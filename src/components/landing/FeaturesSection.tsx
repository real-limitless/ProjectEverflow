import {
  Bot,
  Box,
  Eye,
  GitBranch,
  BookOpen,
  Rocket,
  Terminal,
  ShieldCheck,
} from "lucide-react";

const features = [
  {
    icon: Box,
    title: "MicroVM sandboxes",
    description:
      "Every project boots an isolated microsandbox microVM. Clients talk only to the Everflow API — a privileged sandbox-agent owns KVM and the guest lifecycle.",
  },
  {
    icon: Bot,
    title: "OpenCode & Claude Code",
    description:
      "Chat with coding agents inside the sandbox. Streaming tool calls, generation status, and interactive questions — prebaked into the guest image so agents are ready on first boot.",
  },
  {
    icon: Eye,
    title: "Live preview endpoints",
    description:
      "Discover open ports, mint GUID-hosted preview URLs, and proxy HTTP plus WebSockets so Vite HMR and multi-service stacks work behind the platform.",
  },
  {
    icon: Terminal,
    title: "Interactive terminal & code",
    description:
      "Full xterm shell into the project sandbox, multi-tab code editor with nested explorer and git markers, and panels that stay alive across dock switches.",
  },
  {
    icon: GitBranch,
    title: "Multi-repo workspaces",
    description:
      "Repository panel backed by workspace git — manage multiple remotes, branches, issues, and PRs without leaving the studio workbench.",
  },
  {
    icon: BookOpen,
    title: "Knowledge workbench",
    description:
      "Markdown notes, uploads, and Mermaid architecture maps in one panel — so product context and system diagrams live next to the code agents use.",
  },
  {
    icon: Rocket,
    title: "Deploy workbench",
    description:
      "Remote podman-compose style deploy panel for compose stacks, hosts, and rollout visibility — bridge from sandbox iterate to self-hosted ship.",
  },
  {
    icon: ShieldCheck,
    title: "Governance-first by design",
    description:
      "Orgs, membership, and project isolation keep AI experimentation inside approved boundaries. Build freely without unrestricted access to corporate infrastructure.",
  },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Everything you need to{" "}
            <span className="gradient-text-indigo-teal">vibecode safely</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            A full studio workbench on top of real microVMs — not a thin chat wrapper.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className="group glass rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]"
              style={{ animationDelay: `${index * 100}ms` }}
            >
              <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 transition-transform duration-300 group-hover:scale-110">
                <feature.icon className="h-6 w-6 text-primary" />
              </div>
              <h3 className="font-heading text-lg font-bold text-foreground">
                {feature.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default FeaturesSection;
