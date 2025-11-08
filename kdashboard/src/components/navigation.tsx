'use client';

import {
  Navbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  Link
} from '@heroui/react';
import { usePathname } from 'next/navigation';

export function Navigation() {
  const pathname = usePathname();

  const isActive = (path: string) => {
    if (path === '/' && pathname === '/') return true;
    if (path !== '/' && pathname.startsWith(path)) return true;
    return false;
  };

  return (
    <Navbar isBordered>
      <NavbarBrand>
        <Link href="/" className="font-bold text-inherit">
          kGym Dashboard
        </Link>
      </NavbarBrand>

      <NavbarContent className="hidden sm:flex gap-4" justify="center">
        <NavbarItem>
          <Link
            color={isActive('/') ? 'primary' : 'foreground'}
            href="/"
            aria-current={isActive('/') ? 'page' : undefined}
          >
            Jobs
          </Link>
        </NavbarItem>

        <NavbarItem>
          <Link
            color={isActive('/system/displays/systemLog') ? 'primary' : 'foreground'}
            href="/system/displays/systemLog"
            aria-current={isActive('/system/displays/systemLog') ? 'page' : undefined}
          >
            System Logs
          </Link>
        </NavbarItem>

        <NavbarItem>
          <Link
            color={isActive('/system/displays/jobLog') ? 'primary' : 'foreground'}
            href="/system/displays/jobLog"
            aria-current={isActive('/system/displays/jobLog') ? 'page' : undefined}
          >
            Job Logs
          </Link>
        </NavbarItem>
      </NavbarContent>
    </Navbar>
  );
}