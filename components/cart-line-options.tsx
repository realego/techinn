export function CartLineOptions({ options }: {
  options: { name: string; label: string; price: number }[];
}) {
  if (!options.length) return null;
  return (
    <ul className="text-muted-foreground mt-2 space-y-1 border-l pl-2 text-[10px] leading-relaxed" aria-label="Selected add-ons">
      {options.map((option) => (
        <li key={option.name} className="flex items-start justify-between gap-2">
          <span>{option.name}{option.label === "Add this feature" || option.label.startsWith("Add ") ? "" : `: ${option.label}`}</span>
          <span className="shrink-0 tabular-nums">{option.price === 0 ? "Free" : `+$${option.price.toFixed(2)}`}</span>
        </li>
      ))}
    </ul>
  );
}
