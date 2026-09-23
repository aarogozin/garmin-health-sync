import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { Button, SegmentedControl, StatusBadge } from './UI'

test('shared button retains semantic button behavior and its action tone', () => {
  const onClick = vi.fn()
  render(<Button tone="primary" onClick={onClick}>Refresh data</Button>)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  expect(onClick).toHaveBeenCalledOnce()
  expect(screen.getByRole('button')).toHaveClass('button--primary')
})

test('segmented control reports the active period and changes it accessibly', () => {
  const onChange = vi.fn()
  render(<SegmentedControl value="7d" label="Time period" onChange={onChange} options={[
    { value: '1d', label: 'Today' }, { value: '7d', label: '7 days' },
  ]} />)
  expect(screen.getByRole('button', { name: '7 days' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Today' }))
  expect(onChange).toHaveBeenCalledWith('1d')
})

test('status badge exposes the supplied semantic state for shared styling', () => {
  render(<StatusBadge state="uncertain">Needs review</StatusBadge>)
  expect(screen.getByText('Needs review')).toHaveClass('status-badge--uncertain')
})
