"use client";

import DropdownSelect, {
  type DropdownSelectOption,
} from "@/components/ui/dropdown-select";
import { cn } from "@/lib/utils";

export type SearchableSelectOption = DropdownSelectOption;

type SearchableSelectProps = {
  value?: string;
  onValueChange: (value: string) => void;
  options: SearchableSelectOption[];
  placeholder?: string;
  ariaLabel: string;
  disabled?: boolean;
  triggerClassName?: string;
  contentClassName?: string;
  itemClassName?: string;
  searchEnabled?: boolean;
  searchPlaceholder?: string;
  emptyMessage?: string;
};

const baseTriggerClassName =
  "w-auto h-auto rounded-xl border border-app-border bg-app-surface px-4 py-3 text-left text-sm font-semibold text-app-text shadow-card transition-all duration-200 hover:border-app-border-strong focus:border-app-accent focus:ring-2 focus:ring-app-accent-soft";
const baseContentClassName =
  "rounded-xl border border-app-border bg-app-surface-strong/95 backdrop-blur-glass shadow-panel";
const baseItemClassName =
  "px-4 py-3 text-sm text-app-text-muted transition-colors data-[selected=true]:bg-app-surface-muted data-[selected=true]:text-app-text data-[selected=true]:font-semibold hover:bg-app-surface-muted";

export default function SearchableSelect({
  value,
  onValueChange,
  options,
  placeholder,
  ariaLabel,
  disabled = false,
  triggerClassName,
  contentClassName,
  itemClassName,
  searchEnabled,
  searchPlaceholder,
  emptyMessage,
}: SearchableSelectProps) {
  return (
    <DropdownSelect
      value={value}
      onValueChange={onValueChange}
      options={options}
      placeholder={placeholder}
      ariaLabel={ariaLabel}
      disabled={disabled}
      triggerClassName={cn(baseTriggerClassName, triggerClassName)}
      contentClassName={cn(baseContentClassName, contentClassName)}
      itemClassName={cn(baseItemClassName, itemClassName)}
      searchEnabled={searchEnabled}
      searchPlaceholder={searchPlaceholder}
      emptyMessage={emptyMessage}
    />
  );
}
