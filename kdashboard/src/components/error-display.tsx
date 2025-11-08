'use client';

import { Card, CardBody, Button } from '@heroui/react';

interface ErrorDisplayProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorDisplay({
  title = 'Error',
  message,
  onRetry,
  className = ''
}: ErrorDisplayProps) {
  return (
    <div className={`flex items-center justify-center p-8 ${className}`}>
      <Card className="max-w-md">
        <CardBody className="text-center space-y-4">
          <div>
            <h3 className="text-lg font-semibold text-danger">{title}</h3>
            <p className="text-default-600 mt-2">{message}</p>
          </div>

          {onRetry && (
            <Button
              color="primary"
              variant="flat"
              onPress={onRetry}
            >
              Try Again
            </Button>
          )}
        </CardBody>
      </Card>
    </div>
  );
}