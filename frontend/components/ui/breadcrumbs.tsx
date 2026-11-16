import { ChevronRight, Home } from "lucide-react";

type BreadcrumbsProps = {
  current: string;
};

export function Breadcrumbs({ current }: BreadcrumbsProps) {
  return (
    <nav aria-label="Ruta de navegación" className="flex items-center gap-2 text-sm">
      <a
        aria-label="Inicio"
        className="rounded-md text-muted-foreground hover:text-foreground"
        href="#overview"
      >
        <Home aria-hidden="true" size={15} />
      </a>
      <ChevronRight aria-hidden="true" className="text-slate-300" size={14} />
      <span aria-current="page" className="font-medium text-foreground">
        {current}
      </span>
    </nav>
  );
}
