import { Monitor, HardDrive, ShieldCheck, GitFork } from "lucide-react";

const features = [
  {
    icon: Monitor,
    title: "Vibe Code Anything",
    description: "Build frontend, backend, GUI, or any tech stack. Your AI chatbot gets full access to every resource it needs — databases, APIs, file systems — while safety and compliance layers run automatically in the background.",
    borderColor: "border-primary/20",
    bgColor: "bg-primary/10",
    glowColor: "hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]",
  },
  {
    icon: HardDrive,
    title: "Your Data Never Leaves",
    description: "Everything runs on your local machine. AI models, conversations, and project files stay in containerized environments connected via WebSockets. Zero cloud dependency, zero data leakage.",
    borderColor: "border-primary/20",
    bgColor: "bg-primary/10",
    glowColor: "hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]",
  },
  {
    icon: ShieldCheck,
    title: "Unbreakable AI Guardrails",
    description: "Built-in PII redaction, toxicity filters, and configurable policy enforcement. Fully auditable.",
    borderColor: "border-primary/20",
    bgColor: "bg-primary/10",
    glowColor: "hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]",
  },
  {
    icon: GitFork,
    title: "Fork, Share & Deploy",
    description: "Fork any project, submit PRs, co-edit live, and share templates with the community.",
    borderColor: "border-primary/20",
    bgColor: "bg-primary/10",
    glowColor: "hover:shadow-[0_0_30px_hsl(207,100%,40%,0.12)]",
  },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Build anything.{" "}
            <span className="gradient-text-indigo-teal">Keep everything local.</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            A platform that gives your AI full power while keeping your data fully private.
          </p>
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className={`group glass rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 ${feature.glowColor}`}
              style={{ animationDelay: `${index * 100}ms` }}
            >
              <div className={`mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl ${feature.bgColor} ${feature.borderColor} border transition-transform duration-300 group-hover:scale-110`}>
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
