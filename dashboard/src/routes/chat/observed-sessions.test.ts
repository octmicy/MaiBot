import { describe, expect, it } from 'vitest'

import { getChatStreamDisplayName, type ChatStream } from '@/lib/chat-management-api'

import { buildObservedSessions } from './observed-sessions'

function stream(overrides: Partial<ChatStream>): ChatStream {
  return {
    id: null,
    session_id: 'session',
    display_name: '聊天流',
    chat_type: 'private',
    target_id: '10001',
    platform: 'qq',
    account_id: null,
    scope: null,
    user_id: '10001',
    user_nickname: '用户',
    user_cardname: null,
    group_id: null,
    group_name: null,
    message_count: 0,
    expression_count: 0,
    jargon_count: 0,
    created_at: 1,
    last_active_at: 1,
    latest_message: '',
    latest_message_at: null,
    ...overrides,
  }
}

describe('desktop pet chat stream labels', () => {
  it('uses the referenced stream name and handles missing references', () => {
    const source = stream({ session_id: 'source-1', display_name: '小明的私聊' })
    const pet = stream({
      session_id: 'pet-1',
      platform: 'desktop_pet',
      display_name: '用户owner的私聊',
      scope: source.session_id,
    })
    const orphan = stream({
      session_id: 'pet-2',
      platform: 'desktop_pet',
      display_name: '用户owner的私聊',
      scope: 'deleted-source',
    })
    const unbound = stream({ session_id: 'pet-3', platform: 'desktop_pet', display_name: '用户owner的私聊', scope: null })

    expect(getChatStreamDisplayName(pet, [source, pet])).toBe('桌宠私聊 · 小明的私聊')
    expect(getChatStreamDisplayName(orphan, [orphan])).toBe('桌宠私聊 · 参考聊天流不可用')
    expect(getChatStreamDisplayName(unbound, [unbound])).toBe('桌宠私聊')
  })

  it('uses the same label in observed sessions', () => {
    const source = stream({ session_id: 'source-1', display_name: '项目群' })
    const pet = stream({ session_id: 'pet-1', platform: 'desktop_pet', scope: source.session_id })

    const { sessions } = buildObservedSessions([source, pet], new Map(), new Map())

    expect(sessions.get('pet-1')?.sessionName).toBe('桌宠私聊 · 项目群')
  })
})
