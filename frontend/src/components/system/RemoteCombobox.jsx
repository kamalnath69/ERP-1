import React, { useMemo, useState } from "react";
import { CaretUpDown, Check } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import {
  Command, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export default function RemoteCombobox({
  value,
  onValueChange,
  items = [],
  selectedItem,
  onSearchChange,
  getValue = (item) => item.id,
  getLabel = (item) => item.name || item.display_name || item.id,
  getDescription,
  placeholder = "Choose a record",
  searchPlaceholder = "Search...",
  emptyText = "No matching records",
  loading = false,
  error = false,
  hasMore = false,
  onLoadMore,
  onRetry,
  disabled = false,
  className,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = useMemo(
    () => selectedItem || items.find((item) => getValue(item) === value),
    [getValue, items, selectedItem, value],
  );

  const changeOpen = (nextOpen) => {
    setOpen(nextOpen);
    if (!nextOpen && search) {
      setSearch("");
      onSearchChange?.("");
    }
  };

  return <Popover open={open} onOpenChange={changeOpen}>
    <PopoverTrigger asChild>
      <Button
        type="button"
        variant="outline"
        role="combobox"
        aria-expanded={open}
        disabled={disabled}
        className={cn("h-10 w-full min-w-0 justify-between rounded-xl px-3 font-normal", !selected && "text-muted-foreground", className)}
      >
        <span className="truncate">{selected ? getLabel(selected) : placeholder}</span>
        <CaretUpDown className="ml-2 shrink-0 text-muted-foreground" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-[16rem] p-0">
      <Command shouldFilter={false}>
        <CommandInput
          value={search}
          onValueChange={(nextSearch) => {
            setSearch(nextSearch);
            onSearchChange?.(nextSearch);
          }}
          placeholder={searchPlaceholder}
        />
        <CommandList>
          {loading && !items.length && <div className="px-3 py-6 text-center text-sm text-muted-foreground">Searching...</div>}
          {!loading && !error && !items.length && <div className="px-3 py-6 text-center text-sm text-muted-foreground">{emptyText}</div>}
          {error && !items.length && <div className="space-y-2 px-3 py-5 text-center"><p className="text-sm text-muted-foreground">Could not load records</p>{onRetry && <Button type="button" size="sm" variant="outline" onClick={onRetry}>Try again</Button>}</div>}
          {items.length > 0 && <CommandGroup>
            {items.map((item) => {
              const itemValue = getValue(item);
              const description = getDescription?.(item);
              return <CommandItem
                key={itemValue}
                value={itemValue}
                onSelect={() => {
                  onValueChange?.(itemValue, item);
                  changeOpen(false);
                }}
                className="items-start py-2.5"
              >
                <Check className={cn("mt-0.5 shrink-0", value === itemValue ? "opacity-100" : "opacity-0")} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{getLabel(item)}</span>
                  {description && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{description}</span>}
                </span>
              </CommandItem>;
            })}
          </CommandGroup>}
          {(hasMore || (error && items.length > 0)) && <div className="border-t p-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="w-full"
              disabled={loading}
              onClick={error ? onRetry : onLoadMore}
            >
              {loading ? "Loading..." : error ? "Retry" : "Load more"}
            </Button>
          </div>}
        </CommandList>
      </Command>
    </PopoverContent>
  </Popover>;
}
