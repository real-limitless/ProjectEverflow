import { useEffect, useId, useMemo, useRef, useState } from 'react'
import {
  Button,
  Label,
  LabelGroup,
  MenuToggle,
  type MenuToggleElement,
  Select,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'

export type TypeaheadOption = {
  id: string
  label: string
  description?: string
}

const NO_RESULTS = '__no-results__'
const CREATE_PREFIX = '__create__:'

/**
 * PatternFly v6 multiple typeahead (Select + MenuToggle typeahead + LabelGroup).
 * Selected values render as removable labels under the field — not a wall of the catalog.
 */
export function TypeaheadMultiSelect({
  id,
  ariaLabel,
  placeholder,
  options,
  selected,
  onChange,
  creatable = true,
}: {
  id: string
  ariaLabel: string
  placeholder: string
  options: TypeaheadOption[]
  selected: string[]
  onChange: (next: string[]) => void
  creatable?: boolean
}) {
  const reactId = useId()
  const inputId = `${id}-input`
  const listId = `${id}-listbox`
  const [isOpen, setIsOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [focusedItemIndex, setFocusedItemIndex] = useState<number | null>(null)
  const textInputRef = useRef<HTMLInputElement>(null)

  const catalog = useMemo(() => {
    const byId = new Map<string, TypeaheadOption>()
    for (const opt of options) {
      if (opt.id) byId.set(opt.id, opt)
    }
    for (const value of selected) {
      if (value && !byId.has(value)) byId.set(value, { id: value, label: value })
    }
    return [...byId.values()]
  }, [options, selected])

  const labelOf = (value: string) => catalog.find((o) => o.id === value)?.label || value

  const filtered = useMemo(() => {
    const q = inputValue.trim().toLowerCase()
    const base = q
      ? catalog.filter(
          (o) =>
            o.id.toLowerCase().includes(q) ||
            o.label.toLowerCase().includes(q) ||
            (o.description || '').toLowerCase().includes(q),
        )
      : catalog
    if (base.length === 0) {
      if (creatable && q && !catalog.some((o) => o.id.toLowerCase() === q)) {
        return [{ id: `${CREATE_PREFIX}${inputValue.trim()}`, label: `Add “${inputValue.trim()}”` }]
      }
      return [{ id: NO_RESULTS, label: q ? `No results for “${inputValue.trim()}”` : 'No options' }]
    }
    if (creatable && q && !catalog.some((o) => o.id.toLowerCase() === q || o.label.toLowerCase() === q)) {
      return [...base, { id: `${CREATE_PREFIX}${inputValue.trim()}`, label: `Add “${inputValue.trim()}”` }]
    }
    return base
  }, [catalog, creatable, inputValue])

  useEffect(() => {
    setFocusedItemIndex(null)
  }, [inputValue])

  const closeMenu = () => {
    setIsOpen(false)
    setFocusedItemIndex(null)
  }

  const toggleValue = (raw: string) => {
    if (!raw || raw === NO_RESULTS) return
    const value = raw.startsWith(CREATE_PREFIX) ? raw.slice(CREATE_PREFIX.length) : raw
    if (!value) return
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value])
    setInputValue('')
    textInputRef.current?.focus()
  }

  const onInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!isOpen) setIsOpen(true)
      const last = filtered.length - 1
      if (last < 0) return
      if (event.key === 'ArrowDown') {
        setFocusedItemIndex((i) => (i === null || i === last ? 0 : i + 1))
      } else {
        setFocusedItemIndex((i) => (i === null || i === 0 ? last : i - 1))
      }
      return
    }
    if (event.key === 'Enter') {
      const focused = focusedItemIndex !== null ? filtered[focusedItemIndex] : null
      if (isOpen && focused) toggleValue(focused.id)
      else if (!isOpen) setIsOpen(true)
    }
    if (event.key === 'Escape') closeMenu()
  }

  const toggle = (toggleRef: React.Ref<MenuToggleElement>) => (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      aria-label={ariaLabel}
      onClick={() => setIsOpen((open) => !open)}
      isExpanded={isOpen}
      isFullWidth
    >
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={inputValue}
          onClick={() => setIsOpen(true)}
          onChange={(_e, value) => {
            setInputValue(value)
            setIsOpen(true)
          }}
          onKeyDown={onInputKeyDown}
          id={inputId}
          autoComplete="off"
          innerRef={textInputRef}
          placeholder={placeholder}
          role="combobox"
          isExpanded={isOpen}
          aria-controls={listId}
          aria-label={ariaLabel}
        />
        <TextInputGroupUtilities {...(selected.length === 0 ? { style: { display: 'none' } } : {})}>
          <Button
            variant="plain"
            onClick={() => {
              onChange([])
              setInputValue('')
              textInputRef.current?.focus()
            }}
            aria-label={`Clear ${ariaLabel}`}
            icon={<TimesIcon />}
          />
        </TextInputGroupUtilities>
      </TextInputGroup>
    </MenuToggle>
  )

  return (
    <div className="typeahead-ms" data-typeahead={id}>
      <Select
        id={id || reactId}
        isOpen={isOpen}
        selected={selected}
        onSelect={(_event, selection) => toggleValue(String(selection))}
        onOpenChange={(open) => {
          if (!open) closeMenu()
        }}
        toggle={toggle}
        variant="typeahead"
      >
        <SelectList isAriaMultiselectable id={listId}>
          {filtered.map((option, index) => (
            <SelectOption
              key={option.id}
              value={option.id}
              isFocused={focusedItemIndex === index}
              isSelected={selected.includes(option.id)}
              isDisabled={option.id === NO_RESULTS}
              description={option.description}
            >
              {option.label}
            </SelectOption>
          ))}
        </SelectList>
      </Select>
      {selected.length > 0 ? (
        <LabelGroup aria-label={`${ariaLabel} selected`} className="typeahead-ms__labels" numLabels={8}>
          {selected.map((value) => (
            <Label
              key={value}
              variant="outline"
              onClose={() => toggleValue(value)}
            >
              {labelOf(value)}
            </Label>
          ))}
        </LabelGroup>
      ) : null}
    </div>
  )
}
