// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// Section documentation site.
// Source markdown lives in ../docs and is mirrored into src/content/docs/
// by scripts/sync-docs.mjs (run automatically before build).
export default defineConfig({
  outDir: "./dist",
  integrations: [
    starlight({
      title: "Section",
      description:
        "Open-source AI Security Control Plane & Semantic Data Loss Prevention platform.",
      logo: {
        src: "./src/assets/section-mark.svg",
        replacesTitle: false,
      },
      social: {
        github: "https://github.com/cwellbournewood/section",
      },
      editLink: {
        baseUrl: "https://github.com/cwellbournewood/section/edit/main/docs/",
      },
      lastUpdated: true,
      customCss: ["./src/styles/section.css"],
      defaultLocale: "en",
      sidebar: [
        {
          label: "Getting Started",
          items: [
            { label: "Overview", link: "/" },
            { label: "5-minute quickstart", link: "/getting-started/" },
            {
              label: "Architecture overview",
              link: "/architecture/00-overview/",
            },
          ],
        },
        {
          label: "Architecture",
          items: [
            { label: "Overview", link: "/architecture/00-overview/" },
            { label: "Data flow", link: "/architecture/01-data-flow/" },
            { label: "Gateway", link: "/architecture/02-gateway/" },
            { label: "Policy engine", link: "/architecture/03-policy-engine/" },
            { label: "Semantic DLP", link: "/architecture/04-semantic-dlp/" },
            { label: "Anonymisation", link: "/architecture/05-anonymization/" },
            { label: "Audit & lineage", link: "/architecture/06-audit-lineage/" },
            { label: "Agent governance", link: "/architecture/07-agent-governance/" },
            { label: "Model routing", link: "/architecture/08-model-routing/" },
            { label: "RAG & vector", link: "/architecture/09-rag-vector/" },
            { label: "Deployment", link: "/architecture/10-deployment/" },
          ],
        },
        {
          label: "ADRs",
          autogenerate: { directory: "adr" },
        },
        {
          label: "Compliance",
          autogenerate: { directory: "compliance" },
        },
        {
          label: "Operations",
          autogenerate: { directory: "operations" },
        },
        {
          label: "Security",
          items: [
            { label: "Threat model", link: "/threat-model/" },
            { label: "Red-team playbook", link: "/redteam/playbook/" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "Market research", link: "/market-research/" },
            { label: "Benchmarks", link: "/benchmarks/" },
            { label: "Third-party notices", link: "/third_party/" },
          ],
        },
      ],
    }),
  ],
});
