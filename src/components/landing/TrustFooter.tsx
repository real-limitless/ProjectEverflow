import { ShieldCheck, Lock, Server, Waves } from "lucide-react";

const badges = [
  { icon: Server, label: "Self-hosted Compose" },
  { icon: ShieldCheck, label: "Project isolation" },
  { icon: Lock, label: "Org-scoped access" },
];

const stack = [
  "microsandbox",
  "OpenCode",
  "Claude Code",
  "FastAPI",
  "PatternFly",
  "Podman / Docker",
];

const footerLinks = {
  Product: [
    { label: "Features", href: "#features" },
    { label: "Studio", href: "#studio" },
    { label: "Screenshots", href: "#screenshots" },
    { label: "Architecture", href: "#architecture" },
    { label: "Workflow", href: "#workflow" },
    { label: "Capabilities", href: "#playground" },
  ],
  Platform: [
    { label: "MicroVM sandboxes", href: "#architecture" },
    { label: "Agent harnesses", href: "#features" },
    { label: "Live previews", href: "#screenshots" },
    { label: "Marketplace", href: "#playground" },
    { label: "Workflows", href: "#workflow" },
  ],
  Resources: [
    {
      label: "GitHub",
      href: "https://github.com/real-limitless/ProjectEverflow",
    },
    {
      label: "README",
      href: "https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/README.md",
    },
    {
      label: "Roadmap",
      href: "https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/ROADMAP.md",
    },
    {
      label: "BETA-v0.0.1",
      href: "https://github.com/real-limitless/ProjectEverflow/releases/tag/BETA-v0.0.1",
    },
    {
      label: "Security",
      href: "https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/SECURITY.md",
    },
  ],
  Community: [
    {
      label: "Star the repo",
      href: "https://github.com/real-limitless/ProjectEverflow",
    },
    {
      label: "Issues",
      href: "https://github.com/real-limitless/ProjectEverflow/issues",
    },
    {
      label: "Contributing",
      href: "https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/CONTRIBUTING.md",
    },
    {
      label: "Code of conduct",
      href: "https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/CODE_OF_CONDUCT.md",
    },
  ],
};

const TrustFooter = () => {
  return (
    <>
      <section className="border-t border-border/50 py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="mb-12 flex flex-wrap items-center justify-center gap-6">
            {badges.map((badge) => (
              <div
                key={badge.label}
                className="flex items-center gap-2 rounded-full bg-muted px-4 py-2 text-sm font-medium text-muted-foreground"
              >
                <badge.icon className="h-4 w-4 text-primary" />
                {badge.label}
              </div>
            ))}
          </div>

          <p className="mb-6 text-center text-sm text-muted-foreground">
            Built on open components teams already trust
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8">
            {stack.map((item) => (
              <span
                key={item}
                className="font-heading text-lg font-bold text-muted-foreground/40"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <footer className="relative border-t border-border/50 bg-muted/30 py-16">
        <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent" />

        <div className="container mx-auto px-4 lg:px-8">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-6">
            <div className="lg:col-span-2">
              <a href="#" className="mb-4 flex items-center gap-2">
                <Waves className="h-6 w-6 text-primary" />
                <span className="font-heading text-xl font-bold">everflow</span>
              </a>
              <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
                Governance-first collaborative AI apps on your infrastructure. Isolated microVMs,
                coding agents, live previews, and workflows — self-hosted via Compose.
              </p>
            </div>

            {Object.entries(footerLinks).map(([title, links]) => (
              <div key={title}>
                <h4 className="mb-4 font-heading text-sm font-bold text-foreground">{title}</h4>
                <ul className="space-y-2">
                  {links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        {...(link.href.startsWith("http")
                          ? { target: "_blank", rel: "noopener noreferrer" }
                          : {})}
                        className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-border/50 pt-8 sm:flex-row">
            <p className="text-sm text-muted-foreground">
              © 2026 Project Everflow. Apache License 2.0.
            </p>
            <div className="flex gap-4 text-sm text-muted-foreground">
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors hover:text-foreground"
              >
                GitHub
              </a>
              <a
                href="https://github.com/real-limitless/ProjectEverflow/releases/tag/BETA-v0.0.1"
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors hover:text-foreground"
              >
                Public beta
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
};

export default TrustFooter;
