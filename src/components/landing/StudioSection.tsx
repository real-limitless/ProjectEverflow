import {
  MessageSquare,
  Code2,
  Terminal,
  MonitorPlay,
  GitBranch,
  BookOpen,
  Rocket,
  FlaskConical,
  Workflow,
  Database,
} from "lucide-react";

const panels = [
  {
    icon: MessageSquare,
    name: "Chat",
    blurb: "OpenCode streaming, tools, and agent questions",
  },
  {
    icon: Code2,
    name: "Code",
    blurb: "Multi-tab editor, nested explorer, git markers",
  },
  {
    icon: Terminal,
    name: "Terminal",
    blurb: "Interactive shell inside the project microVM",
  },
  {
    icon: MonitorPlay,
    name: "Preview",
    blurb: "GUID hosts, device modes, WebSocket HMR",
  },
  {
    icon: GitBranch,
    name: "Repos",
    blurb: "Multi-repo workspace git, issues & PRs",
  },
  {
    icon: BookOpen,
    name: "Knowledge",
    blurb: "Markdown workbench + Mermaid system maps",
  },
  {
    icon: Rocket,
    name: "Deploy",
    blurb: "Podman-compose style remote deploy workbench",
  },
  {
    icon: FlaskConical,
    name: "Tests",
    blurb: "Sandbox test runs and result summaries",
  },
  {
    icon: Workflow,
    name: "Workflows",
    blurb: "Visual automation nodes next to your app",
  },
  {
    icon: Database,
    name: "Database",
    blurb: "Harness-backed data tools for the project",
  },
];

const StudioSection = () => {
  return (
    <section id="studio" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            One dockable{" "}
            <span className="gradient-text-indigo-teal">studio workbench</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Playground v2 keeps panels alive across tab switches — chat, code, terminal, and
            preview stay warm while you rearrange the dock.
          </p>
        </div>

        {/* Mock workbench chrome */}
        <div className="mx-auto mb-12 max-w-5xl overflow-hidden rounded-2xl border border-border/80 bg-card shadow-xl">
          <div className="flex items-center gap-2 border-b border-border/60 bg-muted/50 px-4 py-3">
            <div className="flex gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
              <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
              <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
            </div>
            <span className="ml-2 font-mono text-xs text-muted-foreground">
              everflow · playground · project sandbox ready
            </span>
            <span className="ml-auto rounded-full bg-primary/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
              microVM live
            </span>
          </div>
          <div className="grid gap-px bg-border/40 sm:grid-cols-3">
            <div className="bg-background p-4 min-h-[140px]">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                Chat · OpenCode
              </div>
              <div className="space-y-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                <p className="text-foreground/80">Add a health endpoint and wire the preview.</p>
                <p className="text-primary/90">▸ tool · sandbox_write_file</p>
                <p className="text-primary/90">▸ tool · terminal · npm run dev</p>
                <p className="animate-pulse text-muted-foreground/70">streaming…</p>
              </div>
            </div>
            <div className="bg-background p-4 min-h-[140px]">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                Code · multi-tab
              </div>
              <pre className="overflow-hidden font-mono text-[11px] leading-relaxed text-muted-foreground">
                <span className="text-primary/70">1</span>{" "}
                <span className="text-foreground/70">@app.get</span>
                <span className="text-primary">("/health")</span>
                {"\n"}
                <span className="text-primary/70">2</span>{" "}
                <span className="text-foreground/70">def health():</span>
                {"\n"}
                <span className="text-primary/70">3</span>{" "}
                <span className="text-muted-foreground">{"  return {"}</span>
                <span className="text-primary">"ok"</span>
                <span className="text-muted-foreground">{": True}"}</span>
              </pre>
            </div>
            <div className="bg-background p-4 min-h-[140px]">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                Preview · GUID host
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/40 p-3">
                <div className="mb-2 flex gap-1">
                  <span className="h-1.5 w-8 rounded-full bg-primary/40" />
                  <span className="h-1.5 w-12 rounded-full bg-muted-foreground/20" />
                </div>
                <div className="h-16 rounded bg-gradient-to-br from-primary/10 to-primary/5 flex items-center justify-center">
                  <span className="font-mono text-[10px] text-muted-foreground">
                    preview.everflow / ······.local
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {panels.map((panel) => (
            <div
              key={panel.name}
              className="group rounded-xl border border-border/60 bg-card/50 p-4 transition-all hover:border-primary/30 hover:bg-primary/5"
            >
              <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <panel.icon className="h-4 w-4" />
              </div>
              <h3 className="font-heading text-sm font-bold text-foreground">{panel.name}</h3>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{panel.blurb}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default StudioSection;
