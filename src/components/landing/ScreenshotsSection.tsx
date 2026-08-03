import { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Shot = {
  src: string;
  title: string;
  caption: string;
  category: "Platform" | "Create" | "Knowledge" | "Build" | "Agents";
};

const shots: Shot[] = [
  {
    src: "/screenshots/01-playground-home.png",
    title: "Playground home",
    caption: "Open or create a project bound to an isolated microVM sandbox.",
    category: "Platform",
  },
  {
    src: "/screenshots/02-marketplace.png",
    title: "Marketplace",
    caption: "Discover and install skills, tools, and MCP servers for harnesses.",
    category: "Platform",
  },
  {
    src: "/screenshots/03-usage.png",
    title: "Usage dashboard",
    caption: "Token usage per model and per project.",
    category: "Platform",
  },
  {
    src: "/screenshots/playground/01-create-project.png",
    title: "Create project",
    caption: "Name, description, and URL slug for a new sandbox-backed project.",
    category: "Create",
  },
  {
    src: "/screenshots/playground/02-connect-repos.png",
    title: "Connect repositories",
    caption: "Attach Git remotes so agents work on your real codebases.",
    category: "Create",
  },
  {
    src: "/screenshots/playground/03-web-search-knowledge.png",
    title: "Web search",
    caption: "Search the internet and promote results into Knowledge for models.",
    category: "Knowledge",
  },
  {
    src: "/screenshots/playground/04-reader-mode.png",
    title: "Reader mode",
    caption: "Clean extracted page text for review and grounding.",
    category: "Knowledge",
  },
  {
    src: "/screenshots/playground/05-website-view.png",
    title: "Website view",
    caption: "Open the live page in Web search (Website vs Reader).",
    category: "Knowledge",
  },
  {
    src: "/screenshots/playground/06-mind-maps.png",
    title: "Mind maps",
    caption: "AI-built or user-defined maps of project knowledge.",
    category: "Knowledge",
  },
  {
    src: "/screenshots/playground/07-code-editor.png",
    title: "Code editor",
    caption: "Browse the tree, open files, and edit in the workbench.",
    category: "Build",
  },
  {
    src: "/screenshots/playground/08-git-history-graph.png",
    title: "Git history & graph",
    caption: "Commit history, human or AI commits, repo graph.",
    category: "Build",
  },
  {
    src: "/screenshots/playground/09-live-preview.png",
    title: "Live Preview",
    caption: "Chat starts apps in the sandbox; Preview streams them live.",
    category: "Build",
  },
  {
    src: "/screenshots/playground/10-desktop-environment.png",
    title: "Desktop environment",
    caption: "Real GUI desktop for agents — isolated in the project guest.",
    category: "Build",
  },
  {
    src: "/screenshots/playground/11-agents-skills-tools.png",
    title: "Agents, skills & tools",
    caption: "Agents, skills, HTTP tools, MCP servers, and OpenCode plugins.",
    category: "Agents",
  },
  {
    src: "/screenshots/playground/12-sql-database.png",
    title: "SQL database",
    caption: "Run SQL yourself or with AI assistance.",
    category: "Agents",
  },
  {
    src: "/screenshots/playground/13-workflows.png",
    title: "Workflows",
    caption: "Automated pipelines and CI/CD-style profiles for project tasks.",
    category: "Agents",
  },
  {
    src: "/screenshots/playground/14-org-shared-skills.png",
    title: "Shared org skills",
    caption: "Skills the organization can reuse across projects.",
    category: "Agents",
  },
  {
    src: "/screenshots/playground/15-terminal-cli-harnesses.png",
    title: "Terminal & CLI harnesses",
    caption: "Full sandbox shell plus OpenCode, Claude Code, Codex CLI, and more.",
    category: "Agents",
  },
  {
    src: "/screenshots/playground/16-ai-providers.png",
    title: "AI providers",
    caption: "Attach providers at project or org/global scope.",
    category: "Agents",
  },
];

const filters = ["All", "Platform", "Create", "Knowledge", "Build", "Agents"] as const;

const ScreenshotsSection = () => {
  const [filter, setFilter] = useState<(typeof filters)[number]>("All");
  const [selected, setSelected] = useState<Shot | null>(null);

  const filtered = useMemo(
    () => (filter === "All" ? shots : shots.filter((s) => s.category === filter)),
    [filter],
  );

  return (
    <section id="screenshots" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Real product{" "}
            <span className="gradient-text-indigo-teal">screenshots</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Captured from a live full stack — real org, projects, and microVM sandboxes. Not mock
            UI.
          </p>
        </div>

        <div className="mb-10 flex flex-wrap justify-center gap-2">
          {filters.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setFilter(item)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-all ${
                filter === item
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/25"
                  : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground border border-border/60"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((shot) => (
            <button
              key={shot.src}
              type="button"
              onClick={() => setSelected(shot)}
              className="group overflow-hidden rounded-2xl border border-border/70 bg-card text-left shadow-md transition-all hover:-translate-y-1 hover:border-primary/40 hover:shadow-xl"
            >
              <div className="aspect-[16/10] overflow-hidden bg-muted/40">
                <img
                  src={shot.src}
                  alt={shot.title}
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover object-top transition-transform duration-300 group-hover:scale-[1.02]"
                />
              </div>
              <div className="p-4">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <h3 className="font-heading text-base font-bold text-foreground">{shot.title}</h3>
                  <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                    {shot.category}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2">{shot.caption}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle className="font-heading">{selected?.title}</DialogTitle>
            <DialogDescription>{selected?.caption}</DialogDescription>
          </DialogHeader>
          {selected ? (
            <div className="overflow-hidden rounded-xl border border-border/60">
              <img
                src={selected.src}
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

export default ScreenshotsSection;
