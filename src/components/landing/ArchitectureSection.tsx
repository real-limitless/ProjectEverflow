import { Monitor, Server, Cpu, ArrowRight, Search } from "lucide-react";

const columns = [
  {
    icon: Monitor,
    title: "Platform UI",
    label: "Browser workbench",
    description:
      "PatternFly shell with playground dock, marketplace, usage, harnesses, and org surfaces. Talks only to the public Everflow API.",
  },
  {
    icon: Server,
    title: "Platform API",
    label: "Sole public surface",
    description:
      "Auth, orgs, projects, providers, knowledge, marketplace, sandbox proxy, git credentials, and preview tickets — one FastAPI backend teams can audit.",
  },
  {
    icon: Cpu,
    title: "Sandbox agent + microVM",
    label: "Isolated guests",
    description:
      "Privileged control plane owns KVM and microsandbox. Each project gets its own guest; in-sandbox MCP tools power harnesses.",
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
            directly. Compose is the only supported product runtime.
          </p>
        </div>

        <div className="relative grid gap-6 sm:grid-cols-3">
          {columns.map((col, index) => (
            <div key={col.title} className="relative">
              <div className="glass h-full rounded-2xl p-8 text-center">
                <div className="mx-auto mb-4 inline-flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10">
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

        <div className="mx-auto mt-10 grid max-w-4xl gap-4 sm:grid-cols-2">
          <div className="glass rounded-2xl p-6">
            <p className="font-mono text-xs leading-relaxed text-muted-foreground sm:text-sm">
              <span className="text-primary">Browser / UI</span>
              {"  →  "}
              <span className="text-foreground">platform-api</span>
              {"  →  "}
              <span className="text-foreground">sandbox-agent</span>
              {"  →  "}
              <span className="text-primary">microVM guest</span>
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              Plus embedded OCI registry and internal SearXNG for knowledge search — all brought up
              by the install TUI.
            </p>
          </div>
          <div className="glass rounded-2xl p-6">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
              <Search className="h-3.5 w-3.5" />
              Supported install
            </div>
            <p className="font-mono text-xs text-foreground sm:text-sm">
              ./scripts/everflow install
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              Docker Compose or Podman Compose only. Optional{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                SANDBOX_MOCK=true
              </code>{" "}
              for limited dev without KVM — not for product use.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ArchitectureSection;
