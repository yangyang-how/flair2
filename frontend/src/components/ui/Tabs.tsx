/**
 * Tab switcher — V1 design language.
 * Minimal, uppercase, with section color active state.
 */

import { useState } from "react";
import type { ReactNode } from "react";

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
  className?: string;
}

export default function Tabs({
  tabs,
  defaultTab,
  className = "",
}: TabsProps) {
  const [active, setActive] = useState(defaultTab || tabs[0]?.id || "");

  return (
    <div className={className}>
      <div className="flex gap-1 border-b border-[var(--color-border)]">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`px-5 py-2.5 font-ui text-[10px] font-medium uppercase tracking-[0.12em] transition-all duration-200 ${
              active === tab.id
                ? "border-b-2 border-[var(--stud-b)] text-[var(--stud-b)]"
                : "text-[var(--color-text-muted)] hover:text-[var(--color-ink)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="pt-5">
        {tabs.find((t) => t.id === active)?.content}
      </div>
    </div>
  );
}
