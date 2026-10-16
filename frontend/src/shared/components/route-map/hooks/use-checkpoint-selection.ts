import { useState } from 'react'
import type { RoutePlan } from '@/shared/types/route-plan'
import type { CheckpointRef } from '../route-map.types'

interface CheckpointSelection {
    plan: RoutePlan
    checkpoint: CheckpointRef
}

/** The checkpoint whose details are open. Route ids are local to one response, so a new plan clears it. */
const useCheckpointSelection = (plan: RoutePlan) => {
    const [selection, setSelection] = useState<CheckpointSelection | null>(null)
    const selectedCheckpoint = selection?.plan === plan ? selection.checkpoint : null
    const selectCheckpoint = (checkpoint: CheckpointRef) => setSelection({ plan, checkpoint })

    return { selectedCheckpoint, selectCheckpoint }
}

export default useCheckpointSelection
