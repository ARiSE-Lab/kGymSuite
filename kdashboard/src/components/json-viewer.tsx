'use client';

import JsonView from '@uiw/react-json-view';
import { Card, CardBody } from '@heroui/react';

interface JsonViewerProps {
  data: unknown;
  title?: string;
  className?: string;
}

export function JsonViewer({ data, title, className = '' }: JsonViewerProps) {
  return (
    <Card className={className}>
      {title && (
        <div className="px-4 py-2 border-b">
          <h4 className="text-sm font-medium">{title}</h4>
        </div>
      )}
      <CardBody className="p-4">
        <div className="rounded-lg bg-default-50 p-3 overflow-auto">
          <JsonView
            value={data as object}
            style={{
              backgroundColor: 'transparent',
              fontSize: '0.875rem',
            }}
            collapsed={false}
            displayDataTypes={false}
            enableClipboard={true}
          />
        </div>
      </CardBody>
    </Card>
  );
}