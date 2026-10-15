import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
    title: 'Weather-Aware Truck Routing',
    description: 'Compare truck routes by weather risk, load weight, and travel time.',
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
    return (
        <html lang="en">
            <body className="min-h-screen bg-white text-neutral-900 antialiased">{children}</body>
        </html>
    )
}
