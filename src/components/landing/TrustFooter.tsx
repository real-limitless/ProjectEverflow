import { ShieldCheck, Lock, Award, Waves } from "lucide-react";

const badges = [
  { icon: ShieldCheck, label: "SOC 2 Type II" },
  { icon: Lock, label: "GDPR Compliant" },
  { icon: Award, label: "ISO 27001" },
];

const logos = ["Stripe", "Notion", "Linear", "Vercel", "Figma", "Slack"];

const footerLinks = {
  Product: ["Features", "Security", "Roadmap", "Changelog", "Self-Hosting"],
  Community: ["GitHub", "Discord", "Contributing", "Code of Conduct", "Sponsors"],
  Resources: ["Documentation", "API Reference", "Examples", "Blog", "Status"],
  Legal: ["Privacy Policy", "Terms of Service", "Cookie Policy", "DPA"],
};

const TrustFooter = () => {
  return (
    <>
      {/* Trust bar */}
      <section className="py-16 border-t border-border/50">
        <div className="container mx-auto px-4 lg:px-8">
          {/* Badges */}
          <div className="flex flex-wrap items-center justify-center gap-6 mb-12">
            {badges.map((badge) => (
              <div key={badge.label} className="flex items-center gap-2 rounded-full bg-muted px-4 py-2 text-sm font-medium text-muted-foreground">
                <badge.icon className="h-4 w-4 text-primary" />
                {badge.label}
              </div>
            ))}
          </div>

          {/* Logo bar */}
          <p className="mb-6 text-center text-sm text-muted-foreground">
            Trusted by 200+ open-source teams and organizations
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8">
            {logos.map((logo) => (
              <span key={logo} className="font-heading text-lg font-bold text-muted-foreground/40">
                {logo}
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
            {/* Brand column */}
            <div className="lg:col-span-2">
              <a href="#" className="flex items-center gap-2 mb-4">
                <Waves className="h-6 w-6 text-primary" />
                <span className="font-heading text-xl font-bold">everflow</span>
              </a>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
                Open-source AI experimentation with built-in guardrails. Self-host anywhere.
              </p>
            </div>

            {/* Link columns */}
            {Object.entries(footerLinks).map(([title, links]) => (
              <div key={title}>
                <h4 className="font-heading text-sm font-bold text-foreground mb-4">{title}</h4>
                <ul className="space-y-2">
                  {links.map((link) => (
                    <li key={link}>
                      <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-border/50 pt-8 sm:flex-row">
            <p className="text-sm text-muted-foreground">
              © 2026 Everflow. Open source under MIT License.
            </p>
            <div className="flex gap-4 text-sm text-muted-foreground">
              <a href="#" className="hover:text-foreground transition-colors">GitHub</a>
              <a href="#" className="hover:text-foreground transition-colors">Discord</a>
              <a href="#" className="hover:text-foreground transition-colors">Twitter</a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
};

export default TrustFooter;
