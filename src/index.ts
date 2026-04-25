#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execFileSync, spawnSync } from "child_process";
import { writeFileSync, readFileSync, unlinkSync, rmdirSync, mkdtempSync, existsSync } from "fs";
import { join, dirname } from "path";
import { tmpdir } from "os";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPT_PATH = join(__dirname, "..", "scripts", "generate_report.py");

const THEMES = {
  default: {
    primary_color:   [26,  54,  93],
    accent_color:    [201, 160, 48],
    highlight_color: [235, 243, 252],
  },
  navy: {
    primary_color:   [10,  36,  99],
    accent_color:    [255, 195,  0],
    highlight_color: [230, 240, 255],
  },
  charcoal: {
    primary_color:   [45,  45,  45],
    accent_color:    [220,  80, 40],
    highlight_color: [245, 245, 245],
  },
  forest: {
    primary_color:   [20,  83,  45],
    accent_color:    [180, 140, 20],
    highlight_color: [230, 247, 236],
  },
  burgundy: {
    primary_color:   [100,  0, 30],
    accent_color:    [200, 160, 80],
    highlight_color: [250, 235, 240],
  },
};

function checkPython(): string | null {
  for (const cmd of ["python3", "python"]) {
    const result = spawnSync(cmd, ["--version"], { encoding: "utf8" });
    if (result.status === 0) return cmd;
  }
  return null;
}

function checkReportlab(pythonCmd: string): boolean {
  const result = spawnSync(pythonCmd, ["-c", "import reportlab"], { encoding: "utf8" });
  return result.status === 0;
}

function runGenerator(specJson: object): Buffer {
  const pythonCmd = checkPython();
  if (!pythonCmd) {
    throw new Error(
      "Python not found. Install Python 3.8+ and ensure it is on your PATH."
    );
  }
  if (!checkReportlab(pythonCmd)) {
    throw new Error(
      "reportlab is not installed. Run: pip install reportlab matplotlib"
    );
  }
  if (!existsSync(SCRIPT_PATH)) {
    throw new Error(`Generator script not found at ${SCRIPT_PATH}`);
  }

  const tmpDir = mkdtempSync(join(tmpdir(), "pdf-report-"));
  const specPath   = join(tmpDir, "spec.json");
  const outputPath = join(tmpDir, "report.pdf");

  try {
    writeFileSync(specPath, JSON.stringify(specJson, null, 2), "utf8");
    execFileSync(pythonCmd, [SCRIPT_PATH, "--spec", specPath, "--output", outputPath], {
      timeout: 120_000,
      encoding: "utf8",
    });
    return readFileSync(outputPath);
  } finally {
    try { unlinkSync(specPath); }   catch {}
    try { unlinkSync(outputPath); } catch {}
    try { rmdirSync(tmpDir); } catch {}
  }
}

function parseSections(text: string): object[] {
  const headingRe = /^(#{1,3}\s+.+|[A-Z][^a-z\n]{0,60}|(?:\d+[\.\)]\s+).+)$/m;
  const lines = text.split("\n");
  const sections: { heading: string; body: string }[] = [];
  let current: { heading: string; body: string[] } | null = null;

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped) continue;
    const isHeading =
      /^#{1,3}\s/.test(stripped) ||
      (/^[A-Z]/.test(stripped) && stripped.length < 70 && !stripped.endsWith(".") && stripped === stripped.toUpperCase()) ||
      /^\d+[\.\)]\s+[A-Z]/.test(stripped);

    if (isHeading) {
      if (current) {
        sections.push({ heading: current.heading, body: current.body.join("\n\n") });
      }
      current = { heading: stripped.replace(/^#+\s*/, "").replace(/^\d+[\.\)]\s*/, ""), body: [] };
    } else {
      if (!current) {
        current = { heading: "Overview", body: [] };
      }
      current.body.push(stripped);
    }
  }
  if (current) {
    sections.push({ heading: current.heading, body: current.body.join("\n\n") });
  }

  // If no headings detected at all, split on paragraph breaks
  if (sections.length <= 1 && sections[0]?.heading === "Overview") {
    const paras = text.split(/\n{2,}/).filter(p => p.trim());
    if (paras.length > 2) {
      const overview = paras[0];
      const rest = paras.slice(1);
      return [
        { heading: "Overview",    body: overview },
        { heading: "Details",     body: rest.slice(0, Math.ceil(rest.length / 2)).join("\n\n") },
        { heading: "Conclusions", body: rest.slice(Math.ceil(rest.length / 2)).join("\n\n") },
      ];
    }
  }

  return sections;
}

// ---- MCP server ----

const server = new McpServer({
  name: "pdf-report-generator",
  version: "1.0.0",
});

const MetadataSchema = z.object({
  title:          z.string(),
  subtitle:       z.string().optional(),
  author:         z.string().optional().default(""),
  date:           z.string().optional(),
  company:        z.string().optional().default(""),
  department:     z.string().optional(),
  document_id:    z.string().optional(),
  classification: z.string().optional(),
  logo_path:      z.string().optional(),
  page_size:      z.enum(["letter", "a4"]).optional().default("letter"),
  orientation:    z.enum(["portrait", "landscape"]).optional().default("portrait"),
});

const SectionSchema = z.object({
  heading: z.string(),
  body:    z.string(),
  subsections: z.array(z.object({
    heading: z.string(),
    body:    z.string(),
  })).optional().default([]),
});

const TableSchema = z.object({
  title:         z.string().optional().default(""),
  headers:       z.array(z.string()),
  rows:          z.array(z.array(z.string())),
  after_section: z.number().int().optional().default(0),
});

const ChartSchema = z.object({
  title:         z.string().optional().default(""),
  type:          z.enum(["bar", "line", "pie", "horizontal_bar"]).optional().default("bar"),
  labels:        z.array(z.string()),
  datasets:      z.array(z.object({
    label:  z.string().optional().default(""),
    values: z.array(z.number()),
  })),
  after_section: z.number().int().optional().default(0),
});

const ImageSchema = z.object({
  path:          z.string(),
  caption:       z.string().optional().default(""),
  width_inches:  z.number().optional().default(5.0),
  after_section: z.number().int().optional().default(0),
});

const ThemeSchema = z.object({
  primary_color:   z.array(z.number()).length(3).optional(),
  accent_color:    z.array(z.number()).length(3).optional(),
  highlight_color: z.array(z.number()).length(3).optional(),
}).optional();

server.tool(
  "generate_report",
  "Generate a professional PDF report from a structured JSON specification with metadata, sections, tables, charts, and images. Returns the PDF as base64-encoded data.",
  {
    spec: z.object({
      metadata:          MetadataSchema,
      executive_summary: z.string().optional().default(""),
      sections:          z.array(SectionSchema),
      tables:            z.array(TableSchema).optional().default([]),
      charts:            z.array(ChartSchema).optional().default([]),
      images:            z.array(ImageSchema).optional().default([]),
      theme:             ThemeSchema,
    }),
  },
  async ({ spec }) => {
    let pdfBuffer: Buffer;
    try {
      pdfBuffer = runGenerator(spec);
    } catch (err) {
      return {
        content: [{
          type: "text",
          text: `Error generating PDF: ${(err as Error).message}`,
        }],
        isError: true,
      };
    }

    const base64 = pdfBuffer.toString("base64");
    const title  = spec.metadata.title.replace(/[^a-z0-9]/gi, "_").toLowerCase();
    const uri    = `data:application/pdf;base64,${base64}`;

    return {
      content: [
        {
          type: "text",
          text: `PDF report generated successfully (${(pdfBuffer.length / 1024).toFixed(1)} KB).\n\nTitle: ${spec.metadata.title}\nSections: ${spec.sections.length}\nTables: ${spec.tables?.length ?? 0}\nCharts: ${spec.charts?.length ?? 0}`,
        },
        {
          type: "resource",
          resource: {
            uri,
            mimeType: "application/pdf",
            blob: base64,
          },
        },
      ],
    };
  }
);

server.tool(
  "generate_report_from_text",
  "Convert raw text or LLM chat output into a structured PDF report. Pass unstructured text and basic metadata — sections are detected automatically.",
  {
    text:           z.string().describe("Raw text or LLM output to convert into a report"),
    title:          z.string().describe("Report title"),
    author:         z.string().optional().default("").describe("Author name"),
    company:        z.string().optional().default("").describe("Company name"),
    classification: z.string().optional().default("").describe("Classification label: PUBLIC, INTERNAL, CONFIDENTIAL, or empty"),
    theme_name:     z.string().optional().default("default").describe("Theme name: default, navy, charcoal, forest, burgundy"),
  },
  async ({ text, title, author, company, classification, theme_name }) => {
    const sections = parseSections(text);

    // Use first paragraph as exec summary if it's short enough
    const firstSection = sections[0] as any;
    let execSummary = "";
    if (firstSection && firstSection.body) {
      const firstPara = (firstSection.body as string).split("\n\n")[0];
      if (firstPara.length < 600) {
        execSummary = firstPara;
      }
    }

    const year = new Date().getFullYear();
    const seq  = String(Math.floor(Math.random() * 900) + 100);
    const docId = `RPT-${year}-${seq}`;

    const themeKey = (theme_name in THEMES ? theme_name : "default") as keyof typeof THEMES;
    const theme = THEMES[themeKey];

    const spec = {
      metadata: {
        title,
        author: author || "",
        company: company || "",
        date: new Date().toISOString().split("T")[0],
        document_id: docId,
        classification: classification || undefined,
        page_size: "letter" as const,
      },
      executive_summary: execSummary,
      sections,
      tables: [],
      charts: [],
      images: [],
      theme,
    };

    let pdfBuffer: Buffer;
    try {
      pdfBuffer = runGenerator(spec);
    } catch (err) {
      return {
        content: [{ type: "text", text: `Error generating PDF: ${(err as Error).message}` }],
        isError: true,
      };
    }

    const base64 = pdfBuffer.toString("base64");
    const uri    = `data:application/pdf;base64,${base64}`;

    return {
      content: [
        {
          type: "text",
          text: `PDF report generated successfully (${(pdfBuffer.length / 1024).toFixed(1)} KB).\n\nTitle: ${title}\nDocument ID: ${docId}\nSections detected: ${sections.length}\nTheme: ${themeKey}`,
        },
        {
          type: "resource",
          resource: {
            uri,
            mimeType: "application/pdf",
            blob: base64,
          },
        },
      ],
    };
  }
);

server.tool(
  "list_themes",
  "List available color themes for PDF reports.",
  {},
  async () => {
    const themeList = Object.entries(THEMES).map(([name, t]) => ({
      name,
      primary_color:   t.primary_color,
      accent_color:    t.accent_color,
      highlight_color: t.highlight_color,
      description: {
        default:  "Deep navy and gold — classic corporate",
        navy:     "Bright navy and yellow — high-contrast formal",
        charcoal: "Charcoal and red-orange — bold and modern",
        forest:   "Forest green and olive gold — natural and calm",
        burgundy: "Burgundy and bronze — prestigious and warm",
      }[name] ?? "",
    }));

    return {
      content: [{
        type: "text",
        text: JSON.stringify(themeList, null, 2),
      }],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
