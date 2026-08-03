import {
  Bot,
  Box,
  Eye,
  GitBranch,
  BookOpen,
  Workflow,
  Store,
  ShieldCheck,
  Monitor,
  Database,
  Terminal,
  Sparkles,
} from "lucide-react";

const features = [
  {
    icon: Box,
    title: "MicroVM sandboxes",
    description:
      "Every project boots an isolated microsandbox microVM. Clients talk only to the Everflow API — a privileged sandbox-agent owns KVM and the guest lifecycle.",
  },
  {
    icon: Bot,
    title: "Agent harnesses",
    description:
      "OpenCode, Claude Code, Codex CLI, and more run inside the sandbox. Streaming tool calls, skills, MCP servers, and HTTP tools are configured in one workbench surface.",
  },
  {
    icon: Eye,
    title: "Live preview endpoints",
    description:
      "Chat starts apps in the guest; Preview streams them live. Port discovery, GUID-hosted endpoints, and WebSocket proxying keep Vite HMR working through the platform.",
  },
  {
    icon: Monitor,
    title: "Full desktop GUI",
    description:
      "Agents get a real desktop environment for GUI apps and interactive browsers — still isolated inside the project microVM.",
  },
  {
    icon: Terminal,
    title: "Interactive terminal & code",
    description:
      "Full sandbox shell, multi-tab code editor with project tree and git markers, plus dockable panels that stay warm across switches.",
  },
  {
    icon: GitBranch,
    title: "Connect real repositories",
    description:
      "Attach Git remotes so agents work on your codebases. Commit history, human or AI commits, and repo graph live in the workbench.",
  },
  {
    icon: BookOpen,
    title: "Knowledge, search & mind maps",
    description:
      "Web search, reader mode, full website view, and AI-built mind maps so models ground on project knowledge instead of guessing.",
  },
  {
    icon: Database,
    title: "SQL database workbench",
    description:
      "Run SQL yourself or with AI assistance against project data — explore schemas and results without leaving the studio.",
  },
  {
    icon: Workflow,
    title: "Workflows & automation",
    description:
      "n8n-inspired pipelines and CI/CD-style profiles so agents and triggers run project tasks without manual glue.",
  },
  {
    icon: Store,
    title: "Marketplace & org skills",
    description:
      "Discover and install skills, tools, and MCP servers. Share organization skills across projects with team reuse in mind.",
  },
  {
    icon: Sparkles,
    title: "AI providers & usage",
    description:
      "Attach models at project or org/global scope. Track token usage per model and per project so spend stays visible.",
  },
  {
    icon: ShieldCheck,
    title: "Governance-first by design",
    description:
      "Orgs, membership, plans, and project isolation keep AI experimentation inside approved boundaries — data stays on your infrastructure.",
  },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Everything teams need to{" "}
            <span className="gradient-text-indigo-teal">build AI apps safely</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            A full PatternFly studio on real microVMs — playground, marketplace, harnesses, and
            workflows — not a thin chat wrapper.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className="group glass rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]"
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 transition-transform duration-300 group-hover:scale-110">
                <feature.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-heading text-lg font-bold text-foreground">{feature.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
