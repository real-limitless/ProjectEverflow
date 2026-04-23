import { useState, useEffect } from "react";
import { Menu, X, Waves, Github } from "lucide-react";
import { Button } from "@/components/ui/button";

const navLinks = [
  { label: "Features", href: "#features" },
  { label: "Playground", href: "#playground" },
  { label: "Security", href: "#security" },
  { label: "Community", href: "#community" },
];

const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled ? "glass-strong shadow-lg" : "bg-transparent"
      }`}
    >
      <nav className="container mx-auto flex items-center justify-between px-4 py-3 lg:px-8">
        {/* Logo */}
        <a href="#" className="flex items-center gap-2 group">
          <div className="relative">
            <Waves className="h-7 w-7 text-primary transition-transform duration-300 group-hover:scale-110" />
          </div>
          <div className="flex flex-col">
            <span className="font-heading text-xl font-bold tracking-tight text-foreground">Project Everflow</span>
            <span className="hidden text-[10px] font-medium uppercase tracking-widest text-muted-foreground sm:block">
              Enterprise AI Vibecoding
            </span>
          </div>
        </a>

        {/* Center nav */}
        <div className="hidden items-center gap-1 lg:flex">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/10 hover:text-foreground"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Right CTA */}
        <div className="hidden items-center gap-3 lg:flex">
          <a href="#" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
            Documentation
          </a>
          <Button variant="outline" size="sm" className="border-primary/50 text-primary hover:bg-primary/10">
            <Github className="h-4 w-4 mr-1" /> Star on GitHub
          </Button>
          <Button size="sm" className="bg-primary hover:bg-primary/90 text-primary-foreground">
            Get Started
          </Button>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setIsMobileOpen(!isMobileOpen)}
          className="rounded-lg p-2 text-foreground lg:hidden hover:bg-muted"
          aria-label="Toggle menu"
        >
          {isMobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </nav>

      {/* Mobile drawer */}
      {isMobileOpen && (
        <div className="glass-strong border-t lg:hidden animate-fade-in">
          <div className="container mx-auto flex flex-col gap-2 px-4 py-4">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setIsMobileOpen(false)}
                className="rounded-lg px-4 py-3 text-sm font-medium text-muted-foreground hover:bg-accent/10 hover:text-foreground"
              >
                {link.label}
              </a>
            ))}
            <hr className="border-border/50 my-2" />
            <a href="#" className="px-4 py-2 text-sm text-muted-foreground">
              Documentation
            </a>
            <Button variant="outline" className="border-primary/50 text-primary">
              <Github className="h-4 w-4 mr-1" /> Star on GitHub
            </Button>
            <Button className="bg-primary text-primary-foreground">Get Started</Button>
          </div>
        </div>
      )}
    </header>
  );
};

export default Navbar;
