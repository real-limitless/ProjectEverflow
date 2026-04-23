import { Laptop, Container, Wifi } from "lucide-react";

const columns = [
  {
    icon: Laptop,
    title: "Your Machine",
    label: "All data stays here",
    description: "Project files, AI conversations, and generated code live on your local machine. Nothing is uploaded.",
  },
  {
    icon: Container,
    title: "Containerized AI",
    label: "Isolated & secure",
    description: "Your AI chatbot runs inside a containerized environment with full access to databases, APIs, and file systems.",
  },
  {
    icon: Wifi,
    title: "WebSocket Bridge",
    label: "Real-time connection",
    description: "Bidirectional WebSocket communication keeps the UI and container in sync — fast, local, and private.",
  },
];

const ArchitectureSection = () => {
  return (
    <section className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            How it works:{" "}
            <span className="gradient-text-indigo-teal">100% on your machine</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Containers keep everything isolated. WebSockets keep everything connected.
          </p>
        </div>

        <div className="grid gap-8 sm:grid-cols-3">
          {columns.map((col, index) => (
            <div key={col.title} className="glass rounded-2xl p-8 text-center">
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
              {index < columns.length - 1 && (
                <div className="hidden sm:block absolute top-1/2 -right-4 text-muted-foreground/30">
                </div>
              )}
            </div>
          ))}
        </div>

        <p className="mx-auto mt-10 max-w-xl text-center text-sm text-muted-foreground">
          No data is ever sent to external servers. Your environment, your models, your privacy.
        </p>
      </div>
    </section>
  );
};

export default ArchitectureSection;
