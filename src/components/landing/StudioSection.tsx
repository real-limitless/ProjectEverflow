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
  Bot,
  Wrench,
  Monitor,
  Briefcase,
} from "lucide-react";
import ScreenshotFrame from "./ScreenshotFrame";

const panels = [
  { icon: MessageSquare, name: "Chat", blurb: "Agent streaming, tools, and questions" },
  { icon: Code2, name: "Code", blurb: "Tree explorer, multi-tab editor, git markers" },
  { icon: Terminal, name: "Terminal", blurb: "Interactive shell + CLI harnesses" },
  { icon: MonitorPlay, name: "Preview", blurb: "Live apps streamed from the sandbox" },
  { icon: GitBranch, name: "Repos", blurb: "Remotes, history, and graph" },
  { icon: BookOpen, name: "Knowledge", blurb: "Search, reader, mind maps" },
  { icon: Bot, name: "Agents", blurb: "Skills, tools, MCP, plugins" },
  { icon: Workflow, name: "Workflows", blurb: "Automation & CI-style profiles" },
  { icon: Database, name: "Database", blurb: "SQL with optional AI assist" },
  { icon: Monitor, name: "Desktop", blurb: "Full GUI desktop in the guest" },
  { icon: FlaskConical, name: "Tests", blurb: "Sandbox test runs & results" },
  { icon: Rocket, name: "Deploy", blurb: "Remote compose-style shipping" },
  { icon: Wrench, name: "Tools", blurb: "HTTP tools & MCP servers" },
  { icon: Briefcase, name: "Jobs", blurb: "Background task visibility" },
];

const workbenchShots = [
  {
    src: "/screenshots/playground/17-workbench-chat-code.png",
    alt: "Workbench with chat and code panels docked",
    caption: "Chat + Code docked — panels stay warm across tab switches.",
  },
  {
    src: "/screenshots/playground/16-workbench-chat-preview.png",
    alt: "Workbench with chat and live preview",
    caption: "Chat + Preview — iterate while the app streams from the microVM.",
  },
  {
    src: "/screenshots/playground/18-workbench-code-preview.png",
    alt: "Workbench with code and preview panels",
    caption: "Code + Preview — edit and verify in the same dock layout.",
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
            PatternFly shell with a dock engine — chat, code, terminal, preview, and a dozen more
            panels stay ready while you rearrange the layout.
          </p>
        </div>

        <div className="mx-auto mb-10 max-w-5xl">
          <ScreenshotFrame
            src="/screenshots/playground/07-code-editor.png"
            alt="Everflow code editor panel with project tree"
            caption="Code editor — browse the tree, open files, and edit inside the project sandbox workbench."
          />
        </div>

        <div className="mx-auto mb-14 grid max-w-6xl gap-6 lg:grid-cols-3">
          {workbenchShots.map((shot) => (
            <ScreenshotFrame
              key={shot.src}
              src={shot.src}
              alt={shot.alt}
              caption={shot.caption}
              className="shadow-lg"
            />
          ))}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
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
