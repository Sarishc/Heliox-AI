# Heliox Design System

**Enterprise-grade UI components and design guidelines**

Inspired by: Stripe, Datadog, Vercel, OpenAI

---

## 🎨 Overview

The Heliox Design System provides a comprehensive set of components, utilities, and guidelines for building premium, enterprise-grade interfaces. It emphasizes:

- **Visual Hierarchy** - Clear information architecture
- **Consistency** - Unified design language across all pages
- **Accessibility** - WCAG AA compliant
- **Performance** - Optimized for speed and responsiveness
- **Dark Mode** - Full support with seamless switching

---

## 🌈 Color System

### Brand Colors

The primary brand identity uses a deep blue/purple gradient:

```css
brand-50  → brand-900  /* Light to Dark */
#f0f4ff → #312e81
```

**Usage:**
- `brand-600`: Primary actions, links, active states
- `brand-50`: Subtle backgrounds, hover states
- `brand-700/800`: Darker accents, dark mode

### Semantic Colors

```css
success-*   /* Green - Positive actions, growth */
warning-*   /* Amber - Warnings, caution */
danger-*    /* Red - Errors, destructive actions */
info-*      /* Blue - Informational messages */
```

### Neutral Grayscale

```css
gray-50  → gray-900  /* Light to Dark */
```

**Usage:**
- `gray-50/100`: Page backgrounds, cards
- `gray-200/300`: Borders, dividers
- `gray-400/500`: Muted text, placeholders
- `gray-700/800`: Body text
- `gray-900`: Headings, emphasis

---

## 📐 Typography

### Font Family

```css
Primary: Inter (Google Fonts)
Monospace: Menlo, Monaco, Courier New
```

### Type Scale

| Size | Rem | Use Case |
|------|-----|----------|
| `text-xs` | 0.75rem | Captions, labels |
| `text-sm` | 0.875rem | Body text, descriptions |
| `text-base` | 1rem | Default body |
| `text-lg` | 1.125rem | Subheadings |
| `text-xl` | 1.25rem | Small headings |
| `text-2xl` | 1.5rem | Card titles |
| `text-3xl` | 1.875rem | Page headings |
| `text-4xl` | 2.25rem | Hero text |

### Font Weights

```css
font-normal: 400   /* Body text */
font-medium: 500   /* Emphasized text */
font-semibold: 600 /* Subheadings */
font-bold: 700     /* Headings, emphasis */
```

---

## 🧩 Component Library

### Card Component

Premium container for content grouping.

```tsx
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";

<Card variant="elevated" padding="lg" hoverable>
  <CardHeader>
    <CardTitle>Analytics</CardTitle>
    <CardDescription>Key performance metrics</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Content */}
  </CardContent>
  <CardFooter>
    {/* Actions */}
  </CardFooter>
</Card>
```

**Variants:**
- `default` - Standard card with shadow
- `bordered` - Emphasized border
- `elevated` - Large shadow
- `flat` - Minimal styling

**Props:**
- `padding`: "none" | "sm" | "md" | "lg"
- `hoverable`: boolean - Adds hover effect
- `loading`: boolean - Shows skeleton

### KPI Component

Key Performance Indicator display with trends.

```tsx
import { KPI, KPIGrid } from "@/components/ui/KPI";

<KPIGrid columns={4}>
  <KPI
    label="Total Spend"
    value="$47,234"
    change={12.5}
    changeLabel="vs last month"
    icon={<DollarSign />}
    trend="up"
  />
</KPIGrid>
```

**Props:**
- `value`: string | number - Main metric
- `change`: number - Percentage change
- `trend`: "up" | "down" | "neutral"
- `icon`: ReactNode - Icon element
- `loading`: boolean

### Button Component

```tsx
import { Button } from "@/components/ui/Button";

<Button 
  variant="primary" 
  size="md"
  icon={<Plus />}
  iconPosition="left"
  loading={false}
  fullWidth={false}
>
  Create New
</Button>
```

**Variants:**
- `primary` - Brand color, primary actions
- `secondary` - Neutral, secondary actions
- `outline` - Bordered, subtle actions
- `ghost` - Minimal, tertiary actions
- `danger` - Destructive actions

**Sizes:**
- `sm` - Compact buttons
- `md` - Default size
- `lg` - Prominent actions

### Badge Component

Status indicators and labels.

```tsx
import { Badge, DotBadge } from "@/components/ui/Badge";

<Badge variant="success" size="sm">Active</Badge>
<DotBadge variant="success" /> Online
```

**Variants:**
- `default`, `success`, `warning`, `danger`, `info`, `brand`

### Page Header Component

Consistent page headers with breadcrumbs.

```tsx
import { PageHeader } from "@/components/ui/PageHeader";

<PageHeader
  title="Dashboard"
  description="GPU cost analytics and insights"
  breadcrumbs={[
    { label: "Home", href: "/" },
    { label: "Analytics" }
  ]}
  actions={<Button>Export</Button>}
/>
```

### Empty State Component

User-friendly empty states.

```tsx
import { EmptyState } from "@/components/ui/EmptyState";

<EmptyState
  icon={<Database />}
  title="No data yet"
  description="Connect an integration to start seeing analytics"
  action={{
    label: "Add Integration",
    onClick: () => router.push("/integrations"),
    icon: <Plus />
  }}
/>
```

---

## 🏗️ Layout System

### Enterprise Layout

Main application layout with sidebar and topbar.

```tsx
import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";

export default function Page() {
  return (
    <EnterpriseLayout teamName="My Team">
      {/* Page content */}
    </EnterpriseLayout>
  );
}
```

**Features:**
- Responsive sidebar (hidden on mobile)
- Persistent topbar with search, notifications
- Dark mode toggle
- Organization selector
- Consistent spacing and max-width

### Grid System

12-column responsive grid:

```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
  {/* Items */}
</div>
```

**Breakpoints:**
- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px
- `2xl`: 1536px

---

## 🎭 Dark Mode

### Enabling Dark Mode

Dark mode is controlled via the `dark` class on `<html>`:

```tsx
// Toggle dark mode
document.documentElement.classList.toggle("dark");
```

### Color Variables

All colors automatically adjust in dark mode:

```css
/* Light Mode */
--background: #ffffff;
--foreground: #18181b;

/* Dark Mode (.dark) */
--background: #0a0a0a;
--foreground: #fafafa;
```

### Component Support

All components support dark mode out of the box:

```tsx
<Card className="bg-card text-card-foreground">
  {/* Automatically styled for light/dark */}
</Card>
```

---

## ✨ Animations

### Built-in Animations

```css
animate-fade-in    /* Fade in effect */
animate-slide-up   /* Slide up with fade */
animate-shimmer    /* Loading shimmer */
```

**Usage:**

```tsx
<div className="animate-fade-in">
  Content
</div>
```

### Transitions

Standard transition durations:

```css
transition-all duration-200  /* Fast - hover effects */
transition-all duration-300  /* Medium - modals */
transition-all duration-500  /* Slow - page transitions */
```

---

## 📏 Spacing Scale

Based on 4px grid:

```css
p-1  → 0.25rem (4px)
p-2  → 0.5rem (8px)
p-4  → 1rem (16px)
p-6  → 1.5rem (24px)
p-8  → 2rem (32px)
p-12 → 3rem (48px)
p-16 → 4rem (64px)
```

**Consistent Spacing:**
- Cards: `p-6` or `p-8`
- Page margins: `p-6 lg:p-8`
- Grid gaps: `gap-4` or `gap-6`
- Element gaps: `gap-2` or `gap-3`

---

## 🎯 Border Radius

```css
rounded-sm   → 0.375rem  /* Subtle */
rounded      → 0.5rem    /* Default */
rounded-md   → 0.75rem   /* Medium */
rounded-lg   → 1rem      /* Large */
rounded-xl   → 1.5rem    /* Cards */
rounded-2xl  → 2rem      /* Extra large */
rounded-full → 9999px    /* Circles */
```

---

## 🌟 Shadows

```css
shadow-sm  /* Subtle - inputs, buttons */
shadow     /* Default - cards */
shadow-md  /* Medium - dropdowns */
shadow-lg  /* Large - modals */
shadow-xl  /* Extra - popovers */
```

---

## ♿ Accessibility

### Focus Styles

All interactive elements include focus rings:

```tsx
<button className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2">
```

Or use the utility class:

```tsx
<button className="focus-ring">
```

### Color Contrast

All text/background combinations meet WCAG AA standards:
- Regular text: 4.5:1 minimum
- Large text: 3:1 minimum
- UI components: 3:1 minimum

### Keyboard Navigation

- All components are keyboard accessible
- Tab order follows logical flow
- Focus indicators are always visible

---

## 📦 Using the Design System

### Adding a New Page

```tsx
"use client";

import { EnterpriseLayout } from "@/components/layout/EnterpriseLayout";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";

export default function MyPage() {
  return (
    <EnterpriseLayout>
      <PageHeader
        title="My Page"
        description="Page description"
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card>
          {/* Content */}
        </Card>
      </div>
    </EnterpriseLayout>
  );
}
```

### Creating Custom Components

Follow these guidelines:

1. Use design system colors (`text-foreground`, `bg-card`)
2. Include dark mode support
3. Add focus states for interactive elements
4. Support loading states
5. Include TypeScript props interface
6. Document with JSDoc comments

```tsx
/**
 * My Custom Component
 * Brief description of what it does
 */

interface MyComponentProps {
  title: string;
  loading?: boolean;
  className?: string;
}

export function MyComponent({ 
  title, 
  loading = false,
  className = "" 
}: MyComponentProps) {
  return (
    <div className={`bg-card text-card-foreground rounded-xl p-6 ${className}`}>
      {loading ? <Skeleton /> : <h3>{title}</h3>}
    </div>
  );
}
```

---

## 🚀 Best Practices

### Do ✅

- Use semantic HTML (`<nav>`, `<main>`, `<article>`)
- Include ARIA labels for icons
- Test in dark mode
- Use loading states for async data
- Show empty states when no data
- Provide user feedback (toasts, messages)
- Keep components focused and reusable

### Don't ❌

- Hardcode colors (use CSS variables)
- Ignore mobile responsiveness
- Skip loading states
- Use generic error messages
- Create deeply nested components
- Mix spacing units (stick to the scale)

---

## 🎓 Resources

- [Tailwind CSS v4 Docs](https://tailwindcss.com/docs)
- [Next.js App Router](https://nextjs.org/docs)
- [Lucide Icons](https://lucide.dev)
- [Recharts Documentation](https://recharts.org)

---

## 📝 Changelog

### v1.0.0 (Current)

- Initial design system
- Core components (Card, KPI, Button, Badge)
- Enterprise layout with sidebar/topbar
- Dark mode support
- Full documentation

---

**Need help?** Check the component examples in `/components/ui/` or refer to the implementation in `/app/page.tsx`.
