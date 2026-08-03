import { Monitor, Server, Cpu, ArrowRight } from "lucide-react";

const columns = [
  {
    icon: Monitor,
    title: "Studio UI",
    label: "Browser workbench",
    description:
      "Dockable panels for Chat, Code, Terminal, Preview, Repos, Knowledge, Deploy, and more. Talks only to the public Everflow API.",
  },
  {
    icon: Server,
    title: "Platform API",
    label: "Sole public surface",
    description:
      "Auth, orgs, projects, sandbox lifecycle, OpenCode proxy, shell sessions, and preview ticket issuance — one backend teams can audit.",
  },
  {
    icon: Cpu,
    title: "Sandbox agent + microVM",
    label: "Isolated guests",
    description:
      "Privileged control plane owns KVM and microsandbox. Each project gets its own guest image with Node, OpenCode, and Claude Code ready.",
  },
];

const ArchitectureSection = () => {
  return (
    <section id="architecture" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            How it works:{" "}
            <span className="gradient-text-indigo-teal">API in front, microVMs behind</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Isolation is not a slogan — every project is a real guest. Clients never touch KVM
            directly.
          </p>
        </div>

        <div className="relative grid gap-6 sm:grid-cols-3">
          {columns.map((col, index) => (
            <div key={col.title} className="relative">
              <div className="glass rounded-2xl p-8 text-center h-full">
                <div className="mx-auto mb-4 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
                  <col.icon className="h-8 w-8 text-primary" />
                </div>
                <h3 className="font-heading text-xl font-bold text-foreground">{col.title}</h3>
                <span className="mt-1 inline-block text-xs font-medium uppercase tracking-wider text-primary">
                  {col.label}
                </span>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {col.description}
                </p>
              </div>
              {index < columns.length - 1 && (
                <div
                  className="pointer-events-none absolute top-1/2 -right-3 z-10 hidden -translate-y-1/2 text-primary/40 sm:block"
                  aria-hidden
                >
                  <ArrowRight className="h-5 w-5" />
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mx-auto mt-12 max-w-3xl glass rounded-2xl p-6 sm:p-8">
          <p className="font-mono text-xs sm:text-sm text-muted-foreground leading-relaxed">
            <span className="text-primary">project.create</span>
            {" → "}
            <span className="text-foreground">provision microVM</span>
            {" → "}
            <span className="text-foreground">ensure OpenCode</span>
            {" → "}
            <span className="text-foreground">mint preview endpoint</span>
            {" → "}
            <span className="text-primary">studio ready</span>
          </p>
          <p className="mt-4 text-sm text-muted-foreground">
            Run with Docker Compose (UI + API + sandbox-agent). Use{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-foreground">
              SANDBOX_MOCK=true
            </code>{" "}
            for local demos without KVM, or real microsandbox guests when{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-foreground">
              /dev/kvm
            </code>{" "}
            is available.
          </p>
        </div>
      </div>
    </section>
  );
};

export default ArchitectureSection;
