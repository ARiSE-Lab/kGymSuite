'use client';

import { Tabs, Tab, Card, CardBody } from '@heroui/react';
import { JobWorker } from '@/types';
import { JsonViewer } from './json-viewer';

interface WorkerTabsProps {
  workers: JobWorker[];
}

export function WorkerTabs({ workers }: WorkerTabsProps) {
  if (workers.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-default-500">No workers found for this job</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      <Tabs
        aria-label="Job workers"
        placement="top"
        variant="underlined"
        classNames={{
          tabList: "gap-6 w-full relative rounded-none p-0 border-b border-divider",
          cursor: "w-full bg-primary",
          tab: "max-w-fit px-0 h-12",
          tabContent: "group-data-[selected=true]:text-primary"
        }}
      >
        {workers.map((worker, index) => (
          <Tab
            key={index}
            title={
              <div className="flex items-center space-x-2">
                <span className="text-sm font-medium">
                  Worker {index}: {worker.workerType}
                </span>
              </div>
            }
          >
            <div className="py-4 space-y-4">
              {/* Worker Arguments */}
              <div>
                <h4 className="text-lg font-semibold mb-3">Arguments</h4>
                <JsonViewer
                  data={worker.workerArgument}
                  className="mb-4"
                />
              </div>

              {/* Worker Result */}
              <div>
                <h4 className="text-lg font-semibold mb-3">Result</h4>
                {worker.workerResult ? (
                  <JsonViewer
                    data={worker.workerResult}
                  />
                ) : (
                  <Card>
                    <CardBody>
                      <p className="text-default-500 text-center py-4">
                        No result available yet
                      </p>
                    </CardBody>
                  </Card>
                )}
              </div>
            </div>
          </Tab>
        ))}
      </Tabs>
    </div>
  );
}