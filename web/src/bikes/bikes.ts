// Bike kinds and the kinds of ride a default bike applies to, with their labels.
import type { BikeKind, BikeSlot } from '../api/bikes'

export const KIND_LABELS: Record<BikeKind, string> = {
  road: 'Road',
  gravel: 'Gravel',
  tt: 'TT',
  mtb: 'Mountain',
  trainer: 'Trainer',
  other: 'Other',
}

export const SLOT_LABELS: Record<BikeSlot, string> = {
  zwift: 'Zwift',
  indoor: 'Indoor (not Zwift)',
  outdoor: 'Outdoor',
}

export const KINDS = Object.keys(KIND_LABELS) as BikeKind[]
export const SLOTS = Object.keys(SLOT_LABELS) as BikeSlot[]
