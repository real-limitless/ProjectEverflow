import { ShieldCheck, Lock, Server, Waves } from "lucide-react";

const badges = [
  { icon: Server, label: "Self-hosted" },
  { icon: ShieldCheck, label: "Project isolation" },
  { icon: Lock, label: "Org-scoped access" },
];

const stack = [
  "microsandbox",
  "OpenCode",
  "Claude Code",
  "FastAPI",
  "React",
  "Podman",
];

const footerLinks = {
  Product: [
    { label: "Features", href: "#features" },
    { label: "Studio", href: "#studio" },
    { label: "Architecture", href: "#architecture" },
    { label: "Workflow", href: "#workflow" },
    { label: "Capabilities", href: "#playground" },
  ],
  Platform: [
    { label: "MicroVM sandboxes", href: "#architecture" },
    { label: "OpenCode agents", href: "#features" },
    { label: "Live previews", href: "#playground" },
    { label: "Deploy workbench", href: "#features" },
    { label: "Knowledge maps", href: "#studio" },
  ],
  Resources: [
    {
      label: "GitHub",
      href: "https://github.com/real-limitless/ProjectEverflow",
    },
    {
      label: "README",
      href: "https://github.com/real-limitless/ProjectEverflow#readme",
    },
    {
      label: "Compose stack",
      href: "https://github.com/real-limitless/ProjectEverflow#docker-compose",
    },
    {
      label: "API health",
      href: "#architecture",
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
      href: "https://github.com/real-limitless/ProjectEverflow",
    },
  ],
};

const TrustFooter = () => {
  return (
    <>
      {/* Trust bar */}
      <section className="py-16 border-t border-border/50">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="flex flex-wrap items-center justify-center gap-6 mb-12">
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

      {/* Footer */}
      <footer className="relative border-t border-border/50 bg-muted/30 py-16">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent" />

        <div className="container mx-auto px-4 lg:px-8">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-6">
            <div className="lg:col-span-2">
              <a href="#" className="flex items-center gap-2 mb-4">
                <Waves className="h-6 w-6 text-primary" />
                <span className="font-heading text-xl font-bold">everflow</span>
              </a>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
                Governance-first AI development studio. Isolated microVMs, coding agents, live
                previews, and deploy — self-hosted on your infrastructure.
              </p>
            </div>

            {Object.entries(footerLinks).map(([title, links]) => (
              <div key={title}>
                <h4 className="font-heading text-sm font-bold text-foreground mb-4">{title}</h4>
                <ul className="space-y-2">
                  {links.map((link) => (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        {...(link.href.startsWith("http")
                          ? { target: "_blank", rel: "noopener noreferrer" }
                          : {})}
                        className="text-sm text-muted-foreground hover:text-foreground transition-colors"
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
              © 2026 Everflow. Open source under the project license.
            </p>
            <div className="flex gap-4 text-sm text-muted-foreground">
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
};

export default TrustFooter;
