'use client';

import { Spinner } from '@heroui/react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

export function LoadingSpinner({
  size = 'md',
  label = 'Loading...',
  className = ''
}: LoadingSpinnerProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 ${className}`}>
      <Spinner size={size} />
      {label && (
        <p className="text-default-500 mt-2">{label}</p>
      )}
    </div>
  );
}