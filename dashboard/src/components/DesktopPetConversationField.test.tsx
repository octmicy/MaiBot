import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { getAllChatStreams } from '@/lib/chat-management-api'
import type { ChatStream } from '@/lib/chat-management-api'

import { DesktopPetConversationField } from './DesktopPetConversationField'

vi.mock('@/lib/chat-management-api', () => ({ getAllChatStreams: vi.fn() }))
vi.mock('@/host/state', () => ({ useHostRuntime: () => ({ selected_bot_id: null }) }))
vi.mock('@/lib/avatar-url', () => ({ useResolvedAvatarUrl: () => undefined }))

const stream = (overrides: Partial<ChatStream> = {}): ChatStream => ({
  id: 1,
  session_id: 'source-session',
  display_name: '产品讨论群',
  chat_type: 'group',
  target_id: '123456',
  platform: 'qq',
  account_id: 'bot-1',
  scope: null,
  user_id: null,
  user_nickname: null,
  user_cardname: null,
  group_id: '123456',
  group_name: '产品讨论群',
  message_count: 10,
  expression_count: 0,
  jargon_count: 0,
  created_at: 1,
  last_active_at: 2,
  latest_message: '',
  latest_message_at: null,
  ...overrides,
})

function show() {
  const onChange = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <DesktopPetConversationField value="" onChange={onChange} fieldPath="desktop_pet.conversation_session_id" />
    </QueryClientProvider>
  )
  return onChange
}

it('选择已有会话作为只读参考并排除桌宠聊天流', async () => {
  vi.mocked(getAllChatStreams).mockResolvedValue([
    stream(),
    stream({ session_id: 'pet-session', display_name: '麦麦的桌宠对话', platform: 'desktop_pet', scope: 'source-session' }),
  ])
  const onChange = show()

  fireEvent.click(screen.getByRole('button', { name: '选择聊天会话' }))
  const dialog = await screen.findByRole('dialog')
  await waitFor(() => expect(within(dialog).getByRole('button', { name: /产品讨论群/ })).toBeInTheDocument())
  expect(within(dialog).queryByText('麦麦的桌宠对话')).not.toBeInTheDocument()
  expect(within(dialog).getByText(/只读参考/)).toBeInTheDocument()

  fireEvent.click(within(dialog).getByRole('button', { name: /产品讨论群/ }))
  fireEvent.click(within(dialog).getByRole('button', { name: '保存选择' }))
  expect(onChange).toHaveBeenCalledWith('source-session')
})
