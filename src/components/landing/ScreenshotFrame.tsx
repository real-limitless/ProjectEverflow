import { cn } from "@/lib/utils";

type ScreenshotFrameProps = {
  src: string;
  alt: string;
  caption?: string;
  className?: string;
  imgClassName?: string;
  priority?: boolean;
};

/** Browser-style chrome around a real product screenshot. */
const ScreenshotFrame = ({
  src,
  alt,
  caption,
  className,
  imgClassName,
  priority = false,
}: ScreenshotFrameProps) => {
  return (
    <figure className={cn("overflow-hidden rounded-2xl border border-border/80 bg-card shadow-xl", className)}>
      <div className="flex items-center gap-2 border-b border-border/60 bg-muted/50 px-4 py-2.5">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
        </div>
        <span className="ml-2 truncate font-mono text-[11px] text-muted-foreground">
          everflow · live stack
        </span>
      </div>
      <div className="bg-background">
        <img
          src={src}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          className={cn("h-auto w-full object-cover object-top", imgClassName)}
        />
      </div>
      {caption ? (
        <figcaption className="border-t border-border/50 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
};

export default ScreenshotFrame;
