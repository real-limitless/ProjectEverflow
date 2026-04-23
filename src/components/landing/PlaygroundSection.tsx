import { useState } from "react";
import { GitFork, Play, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const filters = ["All", "Templates", "Agents", "Automations", "Most Forked", "New This Week"];

const projects = [
  {
    title: "Weekly Report Summarizer",
    creator: "Sarah K.",
    category: "Templates",
    forks: 142,
    description: "Auto-summarizes Slack channels and creates executive weekly reports with key metrics.",
    color: "from-primary/15 to-primary/5",
  },
  {
    title: "Customer Onboarding Agent",
    creator: "Marcus T.",
    category: "Agents",
    forks: 89,
    description: "Interactive AI agent that guides new customers through setup, configuration, and first-value moments.",
    color: "from-primary/10 to-primary/20",
  },
  {
    title: "Creative Brainstorm Buddy",
    creator: "Ava L.",
    category: "Agents",
    forks: 203,
    description: "AI-powered brainstorming partner that generates campaign ideas, taglines, and visual concepts.",
    color: "from-primary/20 to-primary/10",
  },
  {
    title: "Code Review Assistant",
    creator: "Dev Team",
    category: "Automations",
    forks: 317,
    description: "Automated code review agent that checks for security vulnerabilities, style issues, and performance.",
    color: "from-primary/10 to-primary/15",
  },
  {
    title: "Meeting Notes AI",
    creator: "Jordan P.",
    category: "Templates",
    forks: 156,
    description: "Records, transcribes, and creates actionable summaries from any meeting with automatic task extraction.",
    color: "from-primary/15 to-primary/10",
  },
  {
    title: "Data Pipeline Builder",
    creator: "Eng Team",
    category: "Automations",
    forks: 94,
    description: "Visual data pipeline builder with AI-generated transformations and automatic error handling.",
    color: "from-primary/20 to-primary/5",
  },
];

const PlaygroundSection = () => {
  const [activeFilter, setActiveFilter] = useState("All");
  const [selectedProject, setSelectedProject] = useState<typeof projects[0] | null>(null);

  const filtered = activeFilter === "All" || activeFilter === "Most Forked" || activeFilter === "New This Week"
    ? projects
    : projects.filter((p) => p.category === activeFilter);

  return (
    <section id="playground" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Watch real{" "}
            <span className="gradient-text-pink">Vibecoding</span>{" "}
            happen
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Explore projects built by the community.
          </p>
        </div>

        {/* Filter chips */}
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

        {/* Project grid */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((project) => (
            <div
              key={project.title}
              className="group glass rounded-2xl overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
            >
              {/* Thumbnail */}
              <div className={`h-32 bg-gradient-to-br ${project.color} flex items-center justify-center`}>
                <div className="font-mono text-xs text-muted-foreground/60 bg-card/50 rounded-lg px-3 py-2 backdrop-blur">
                  {`> everflow run "${project.title.toLowerCase().replace(/ /g, "-")}"`}
                </div>
              </div>

              <div className="p-5">
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20">
                    <User className="h-3 w-3 text-primary" />
                  </div>
                  <span className="text-xs text-muted-foreground">{project.creator}</span>
                  <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
                    <GitFork className="h-3 w-3" /> {project.forks}
                  </span>
                </div>

                <h3 className="font-heading text-base font-bold text-foreground">{project.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{project.description}</p>

                <Button
                  size="sm"
                  className="mt-4 w-full bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground transition-all"
                  onClick={() => setSelectedProject(project)}
                >
                  <Play className="h-4 w-4 mr-1" /> Try it Live
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sandbox modal */}
      <Dialog open={!!selectedProject} onOpenChange={() => setSelectedProject(null)}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="font-heading">{selectedProject?.title}</DialogTitle>
            <DialogDescription>{selectedProject?.description}</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl bg-foreground p-6 font-mono text-sm text-primary-foreground">
            <div className="mb-2 text-primary-foreground/60">$ git clone https://github.com/everflow/{selectedProject?.title.toLowerCase().replace(/ /g, "-")}</div>
            <div className="text-primary">✓ Sandbox initialized</div>
            <div className="text-primary">✓ Guardrails active (PII, toxicity, policy)</div>
            <div className="text-primary-foreground/60">→ Ready to vibecode! Type your prompt...</div>
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
