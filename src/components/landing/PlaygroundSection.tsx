import { useState } from "react";
import {
  Box,
  Bot,
  Eye,
  GitBranch,
  BookOpen,
  Workflow,
  Monitor,
  Database,
  Store,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

const filters = ["All", "Agents", "Runtime", "Knowledge", "Platform"];

const capabilities = [
  {
    title: "OpenCode & multi-harness chat",
    category: "Agents",
    icon: Bot,
    badge: "Streaming",
    image: "/screenshots/playground/11-agents-skills-tools.png",
    description:
      "Chat with coding agents inside the project microVM — skills, HTTP tools, MCP servers, and OpenCode plugins in one place.",
  },
  {
    title: "CLI harnesses in terminal",
    category: "Agents",
    icon: Box,
    badge: "Guest shell",
    image: "/screenshots/playground/15-terminal-cli-harnesses.png",
    description:
      "Full sandbox shell plus OpenCode, Claude Code, Codex CLI, and other harnesses on a prebaked guest image.",
  },
  {
    title: "Live preview + HMR",
    category: "Runtime",
    icon: Eye,
    badge: "WebSocket",
    image: "/screenshots/playground/09-live-preview.png",
    description:
      "Agents start apps in the sandbox; Preview streams them live with GUID hosts and WebSocket proxying for Vite HMR.",
  },
  {
    title: "Desktop environment",
    category: "Runtime",
    icon: Monitor,
    badge: "GUI",
    image: "/screenshots/playground/10-desktop-environment.png",
    description:
      "Real desktop GUI for agents — interactive browsers and GUI apps stay isolated in the project guest.",
  },
  {
    title: "Connect repositories",
    category: "Runtime",
    icon: GitBranch,
    badge: "Git",
    image: "/screenshots/playground/02-connect-repos.png",
    description:
      "Attach remotes so the workbench and agents operate on your real codebases, with history and graph views.",
  },
  {
    title: "Web search & knowledge",
    category: "Knowledge",
    icon: BookOpen,
    badge: "Grounding",
    image: "/screenshots/playground/03-web-search-knowledge.png",
    description:
      "Search the internet, open reader or full website view, and promote results into Knowledge canvases models can use.",
  },
  {
    title: "Mind maps",
    category: "Knowledge",
    icon: BookOpen,
    badge: "Maps",
    image: "/screenshots/playground/06-mind-maps.png",
    description:
      "AI-built or user-defined mind maps that capture project knowledge for grounding.",
  },
  {
    title: "SQL database",
    category: "Agents",
    icon: Database,
    badge: "Data",
    image: "/screenshots/playground/12-sql-database.png",
    description:
      "Run SQL yourself or with AI assistance against project data from the workbench.",
  },
  {
    title: "Workflows engine",
    category: "Agents",
    icon: Workflow,
    badge: "Automation",
    image: "/screenshots/playground/13-workflows.png",
    description:
      "n8n-inspired pipelines and CI/CD-style profiles so agents and triggers run tasks without manual glue.",
  },
  {
    title: "Marketplace",
    category: "Platform",
    icon: Store,
    badge: "Catalog",
    image: "/screenshots/02-marketplace.png",
    description:
      "Discover and install skills, tools, and MCP servers for project harnesses — plus org-shared skills across teams.",
  },
  {
    title: "AI providers",
    category: "Platform",
    icon: Bot,
    badge: "Keys",
    image: "/screenshots/playground/16-ai-providers.png",
    description:
      "Attach providers at project or org/global scope so chat and harnesses use your models and keys.",
  },
  {
    title: "Usage visibility",
    category: "Platform",
    icon: Eye,
    badge: "Spend",
    image: "/screenshots/03-usage.png",
    description:
      "Token usage by model and by project so teams can track AI spend and activity.",
  },
];

const PlaygroundSection = () => {
  const [activeFilter, setActiveFilter] = useState("All");
  const [selected, setSelected] = useState<(typeof capabilities)[0] | null>(null);

  const filtered =
    activeFilter === "All"
      ? capabilities
      : capabilities.filter((c) => c.category === activeFilter);

  return (
    <section id="playground" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Capabilities{" "}
            <span className="gradient-text-pink">shipping in beta</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Surfaces from BETA-v0.0.1 / Development-Everflow — microVMs, agents, knowledge, and
            platform governance.
          </p>
        </div>

        <div className="mb-10 flex flex-wrap justify-center gap-2">
          {filters.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => setActiveFilter(filter)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-all ${
                activeFilter === filter
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/25"
                  : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
              }`}
            >
              {filter}
            </button>
          ))}
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((item) => (
            <div
              key={item.title}
              className="group glass flex flex-col overflow-hidden rounded-2xl transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
            >
              <div className="aspect-[16/10] overflow-hidden border-b border-border/50 bg-muted/30">
                <img
                  src={item.image}
                  alt={item.title}
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover object-top transition-transform duration-300 group-hover:scale-[1.03]"
                />
              </div>
              <div className="flex flex-1 flex-col p-5">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                    <item.icon className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-heading text-base font-bold text-foreground">
                      {item.title}
                    </h3>
                    <span className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                      {item.badge}
                    </span>
                  </div>
                </div>
                <p className="mt-3 flex-1 text-sm text-muted-foreground line-clamp-3">
                  {item.description}
                </p>
                <Button
                  size="sm"
                  className="mt-4 w-full bg-primary/10 text-primary transition-all hover:bg-primary hover:text-primary-foreground"
                  onClick={() => setSelected(item)}
                >
                  <Play className="mr-1 h-4 w-4" /> View capture
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-heading">{selected?.title}</DialogTitle>
            <DialogDescription>{selected?.description}</DialogDescription>
          </DialogHeader>
          {selected ? (
            <div className="overflow-hidden rounded-xl border border-border/60">
              <img
                src={selected.image}
                alt={selected.title}
                className="h-auto w-full object-contain"
              />
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
};

export default PlaygroundSection;
