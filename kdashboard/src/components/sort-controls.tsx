'use client';

import { Select, SelectItem } from '@heroui/react';
import { SortingMode } from '@/types';

interface SortControlsProps {
  sortBy: SortingMode;
  onSortChange: (sortBy: SortingMode) => void;
  className?: string;
}

const sortOptions = [
  { value: 'modifiedTime', label: 'Last Modified' },
  { value: 'createdTime', label: 'Created Time' },
];

export function SortControls({
  sortBy,
  onSortChange,
  className = ''
}: SortControlsProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-sm text-default-600">Sort by:</span>
      <Select
        size="sm"
        value={sortBy}
        onSelectionChange={(value) => {
          const selectedSort = Array.from(value)[0] as SortingMode;
          onSortChange(selectedSort);
        }}
        className="w-40"
        disallowEmptySelection
      >
        {sortOptions.map((option) => (
          <SelectItem key={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </Select>
    </div>
  );
}