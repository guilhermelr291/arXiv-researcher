"use client"

import { use } from "react"

import { Chat } from "../../../components/Chat"

export default function ThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>
}) {
  const { threadId } = use(params)
  return <Chat threadId={threadId} hydrate />
}
