'use client';

import {
  Pagination as HeroUIPagination,
  Select,
  SelectItem,
  Button,
  ButtonGroup
} from '@heroui/react';

interface PaginationProps {
  currentPage: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  className?: string;
}

const pageSizeOptions = [
  { value: '10', label: '10 per page' },
  { value: '20', label: '20 per page' },
  { value: '50', label: '50 per page' },
  { value: '100', label: '100 per page' },
];

export function Pagination({
  currentPage,
  totalItems,
  pageSize,
  onPageChange,
  onPageSizeChange,
  className = ''
}: PaginationProps) {
  const totalPages = Math.ceil(totalItems / pageSize);
  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  if (totalItems === 0) {
    return null;
  }

  return (
    <div className={`flex flex-col sm:flex-row items-center justify-between gap-4 ${className}`}>
      {/* Items info and page size selector */}
      <div className="flex items-center gap-4">
        <div className="text-sm text-default-600">
          Showing {startItem}-{endItem} of {totalItems} items
        </div>

        <Select
          size="sm"
          value={pageSize.toString()}
          onSelectionChange={(value) => {
            const size = parseInt(Array.from(value)[0] as string);
            onPageSizeChange(size);
          }}
          className="w-32"
          disallowEmptySelection
        >
          {pageSizeOptions.map((option) => (
            <SelectItem key={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </Select>
      </div>

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2">
          <ButtonGroup size="sm" variant="flat">
            <Button
              isDisabled={currentPage === 1}
              onPress={() => onPageChange(currentPage - 1)}
            >
              Previous
            </Button>
            <Button
              isDisabled={currentPage === totalPages}
              onPress={() => onPageChange(currentPage + 1)}
            >
              Next
            </Button>
          </ButtonGroup>

          <HeroUIPagination
            total={totalPages}
            page={currentPage}
            onChange={onPageChange}
            size="sm"
            showControls={false}
            classNames={{
              wrapper: "gap-0 overflow-visible",
              item: "w-8 h-8 text-sm",
            }}
          />
        </div>
      )}
    </div>
  );
}