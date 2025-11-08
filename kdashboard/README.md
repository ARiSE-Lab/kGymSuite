# kGym Dashboard

A modern, responsive dashboard for monitoring and managing kGym distributed job system.

## Features

- **Jobs Management**: View, monitor, and navigate job executions with pagination and sorting
- **Individual Job Details**: Comprehensive job information with worker details and JSON data viewers
- **System Logs**: Monitor system-wide activity and events
- **Job Logs**: Track job-specific logs across all jobs
- **Runtime Configuration**: Configurable API endpoint without rebuilding
- **Responsive Design**: Works seamlessly on desktop and mobile devices

## Configuration

The dashboard uses runtime configuration located at `public/config.json`:

```json
{
  "kGymAPIEndpoint": "https://gym-api.example.com"
}
```

You can modify this file to point to your kGym API endpoint without rebuilding the application.

## Development

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Production

1. Build the application:
   ```bash
   npm run build
   ```

2. Start the production server:
   ```bash
   npm start
   ```

## API Integration

The dashboard integrates with the following kGym API endpoints:

- `GET /jobs` - List jobs with pagination and sorting
- `GET /jobs/{jobId}` - Get specific job details
- `GET /jobs/{jobId}/log` - Get job-specific logs
- `GET /system/displays/systemLog` - Get system logs
- `GET /system/displays/jobLog` - Get all job logs

## Technology Stack

- **Framework**: Next.js 15 with App Router
- **UI Components**: HeroUI (NextUI successor)
- **Styling**: Tailwind CSS
- **Language**: TypeScript
- **Date Handling**: date-fns
- **JSON Viewer**: @uiw/react-json-view

## Project Structure

```
src/
├── app/                    # Next.js app router pages
│   ├── jobs/[jobId]/      # Individual job detail pages
│   └── system/displays/   # System and job log pages
├── components/            # Reusable UI components
├── hooks/                 # Custom React hooks
├── lib/                   # Utilities and API client
└── types.tsx             # TypeScript type definitions
```

## Key Components

- **JobCard**: Summary view of jobs in the main listing
- **JobDetailsTable**: Comprehensive job information display
- **WorkerTabs**: Tabbed interface for job workers with JSON viewers
- **LogEntry**: Formatted log entry display
- **Pagination**: Reusable pagination with page size controls
- **JsonViewer**: Collapsible JSON data viewer