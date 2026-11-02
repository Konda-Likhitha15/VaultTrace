type PlaceholderProps = { title: string };

export function Placeholder({ title }: PlaceholderProps) {
  return <div className="rounded border border-gray-200 bg-white p-4">{title}</div>;
}
