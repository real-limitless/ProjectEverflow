import { useMemo, useState } from 'react'
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  SearchInput,
} from '@patternfly/react-core'
import OutlinedStarIcon from '@patternfly/react-icons/dist/esm/icons/outlined-star-icon'
import StarIcon from '@patternfly/react-icons/dist/esm/icons/star-icon'
import type { CatalogItem } from '@/data/chatCatalog'

interface ModelBrowseModalProps {
  isOpen: boolean
  onClose: () => void
  models: CatalogItem[]
  selectedId: string
  pinnedIds: string[]
  onSelect: (id: string) => void
  onTogglePin: (id: string) => void
}

export function ModelBrowseModal({
  isOpen,
  onClose,
  models,
  selectedId,
  pinnedIds,
  onSelect,
  onTogglePin,
}: ModelBrowseModalProps) {
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = !needle
      ? models
      : models.filter(
          (m) =>
            m.id.toLowerCase().includes(needle) ||
            m.label.toLowerCase().includes(needle) ||
            (m.description || '').toLowerCase().includes(needle),
        )
    // Pinned first, then alpha by label
    const pinSet = new Set(pinnedIds)
    return [...list].sort((a, b) => {
      const ap = pinSet.has(a.id) ? 0 : 1
      const bp = pinSet.has(b.id) ? 0 : 1
      if (ap !== bp) return ap - bp
      return a.label.localeCompare(b.label)
    })
  }, [models, pinnedIds, q])

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Browse OpenCode models"
    >
      <ModalHeader title="Browse models" description="Models available in OpenCode for this sandbox" />
      <ModalBody>
        <SearchInput
          placeholder="Search models…"
          value={q}
          onChange={(_e, v) => setQ(v)}
          onClear={() => setQ('')}
          aria-label="Search models"
          className="model-browse-search"
        />
        <p className="model-browse-hint">
          Star a model to pin it in the chat composer menu. Free / built-in OpenCode models work
          without connecting a paid provider key.
        </p>
        <ul className="model-browse-list" role="listbox" aria-label="Models">
          {filtered.length === 0 ? (
            <li className="model-browse-empty">No models match your search.</li>
          ) : (
            filtered.map((m) => {
              const pinned = pinnedIds.includes(m.id)
              const selected = m.id === selectedId
              return (
                <li key={m.id} className={`model-browse-row${selected ? ' is-selected' : ''}`}>
                  <button
                    type="button"
                    className="model-browse-pin"
                    title={pinned ? 'Unpin from menu' : 'Pin to menu'}
                    aria-label={pinned ? `Unpin ${m.label}` : `Pin ${m.label}`}
                    onClick={() => onTogglePin(m.id)}
                  >
                    {pinned ? <StarIcon /> : <OutlinedStarIcon />}
                  </button>
                  <button
                    type="button"
                    className="model-browse-select"
                    onClick={() => {
                      onSelect(m.id)
                      onClose()
                    }}
                  >
                    <span className="model-browse-label">{m.label}</span>
                    <span className="model-browse-meta">
                      {m.description || m.id}
                      {selected ? ' · selected' : ''}
                    </span>
                  </button>
                </li>
              )
            })
          )}
        </ul>
      </ModalBody>
      <ModalFooter>
        <Button variant="link" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  )
}
