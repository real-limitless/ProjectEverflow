import { useState } from "react";
import { Box, Bot, Eye, GitBranch, BookOpen, Rocket, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

const filters = ["All", "Agents", "Runtime", "Git", "Deploy", "Knowledge"];

const capabilities = [
  {
    title: "OpenCode agent session",
    category: "Agents",
    icon: Bot,
    badge: "Streaming",
    description:
      "Chat with OpenCode inside the project microVM — tool calls, file edits, and clarifying questions stream into the Chat panel.",
    demo: [
      "$ everflow project create my-app --harness agent-opencode",
      "✓ microVM provisioned",
      "✓ OpenCode host ensured",
      "→ Chat panel: streaming tools…",
    ],
  },
  {
    title: "Claude Code harness",
    category: "Agents",
    icon: Bot,
    badge: "Guest image",
    description:
      "Prebaked guest image includes Claude Code alongside OpenCode so agent CLIs are warm on first project create.",
    demo: [
      "$ guest image: everflow-sandbox-guest",
      "✓ Node + Claude Code + OpenCode",
      "✓ harness agent-claude-code enabled",
      "→ Ready for agentic edits",
    ],
  },
  {
    title: "GUID preview + HMR",
    category: "Runtime",
    icon: Eye,
    badge: "WebSocket",
    description:
      "Discover sandbox ports, mint GUID-hosted preview endpoints, and proxy HTTP/WebSocket so Vite HMR survives the edge.",
    demo: [
      "$ everflow preview mint --project … --port 5173",
      "✓ endpoint ab12…xyz.preview",
      "✓ HTTP + WS tunnel multiplexed",
      "→ Live reload through proxy",
    ],
  },
  {
    title: "Interactive sandbox shell",
    category: "Runtime",
    icon: Box,
    badge: "xterm",
    description:
      "Full interactive terminal into the project sandbox — not a fake log tail. Run installs, servers, and debug sessions live.",
    demo: [
      "$ attach shell · project sandbox",
      "root@microvm:/workspace# npm run dev",
      "✓ VITE ready on :5173",
      "→ Pair with Preview panel",
    ],
  },
  {
    title: "Multi-repo workspace",
    category: "Git",
    icon: GitBranch,
    badge: "Repos",
    description:
      "Repository panel for multi-remote workspaces — branches, commits, issues, and PRs scoped per repo in one project.",
    demo: [
      "$ workspace repos: web · api · docs",
      "✓ git status markers in Code",
      "✓ issues/PRs filtered by repo",
      "→ Switch active remote anytime",
    ],
  },
  {
    title: "Knowledge + Mermaid maps",
    category: "Knowledge",
    icon: BookOpen,
    badge: "Workbench",
    description:
      "Markdown notes, uploads, and Mermaid architecture diagrams next to the agents that should respect them.",
    demo: [
      "$ knowledge · architecture.md",
      "✓ Mermaid map rendered",
      "✓ notes indexed for context",
      "→ Agents see project truth",
    ],
  },
  {
    title: "Podman-compose deploy",
    category: "Deploy",
    icon: Rocket,
    badge: "Workbench",
    description:
      "Deploy panel modeled as a remote compose workbench — hosts, stacks, and rollout visibility from the same studio.",
    demo: [
      "$ deploy workbench · compose",
      "✓ host online",
      "✓ stack plan ready",
      "→ Ship from sandbox iterate",
    ],
  },
  {
    title: "Project templates & harnesses",
    category: "Agents",
    icon: Box,
    badge: "Wizard",
    description:
      "Create-project wizard with templates and editable harnesses so Claude Code, OpenCode, CI, and preview stay configurable after create.",
    demo: [
      "$ create wizard · template full-stack",
      "✓ harnesses: opencode, preview, ci",
      "✓ settings editable post-create",
      "→ Empty splash → workbench",
    ],
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
            <span className="gradient-text-pink">shipping today</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Real surfaces from the Everflow platform — microVMs, agents, previews, and deploy.
          </p>
        </div>

        <div className="mb-10 flex flex-wrap justify-center gap-2">
          {filters.map((filter) => (
            <button
              key={filter}
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

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {filtered.map((item) => (
            <div
              key={item.title}
              className="group glass rounded-2xl overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-lg flex flex-col"
            >
              <div className="flex items-start gap-3 p-5 pb-0">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 border border-primary/20">
                  <item.icon className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-heading text-base font-bold text-foreground">
                      {item.title}
                    </h3>
                  </div>
                  <span className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                    {item.badge}
                  </span>
                </div>
              </div>
              <p className="mt-3 px-5 text-sm text-muted-foreground line-clamp-3 flex-1">
                {item.description}
              </p>
              <div className="p-5 pt-4">
                <Button
                  size="sm"
                  className="w-full bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground transition-all"
                  onClick={() => setSelected(item)}
                >
                  <Play className="h-4 w-4 mr-1" /> See flow
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="font-heading">{selected?.title}</DialogTitle>
            <DialogDescription>{selected?.description}</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl bg-foreground p-6 font-mono text-sm text-primary-foreground space-y-1">
            {selected?.demo.map((line, i) => (
              <div
                key={i}
                className={
                  line.startsWith("✓")
                    ? "text-primary"
                    : line.startsWith("→")
                      ? "text-primary-foreground/80"
                      : "text-primary-foreground/60"
                }
              >
                {line}
              </div>
            ))}
            <div className="mt-4 flex items-center gap-2">
              <span className="text-primary">▶</span>
              <span className="animate-pulse">_</span>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
};

export default PlaygroundSection;
