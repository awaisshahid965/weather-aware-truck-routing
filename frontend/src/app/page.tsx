import TripContainer from '@/context/trip/trip.container'
import TripPlanner from '@/shared/components/trip-planner/trip-planner'

export default function Home() {
    return (
        <main className="flex min-h-dvh flex-col lg:h-dvh">
            <header className="border-b border-neutral-200 px-4 py-3">
                <h1 className="text-xl font-semibold">Weather-Aware Truck Routing</h1>
            </header>
            <TripContainer>
                <TripPlanner />
            </TripContainer>
        </main>
    )
}
