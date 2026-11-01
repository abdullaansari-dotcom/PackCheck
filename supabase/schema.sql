-- Run this once in the Supabase SQL editor.

create table if not exists public.scans (
  id                 uuid primary key default gen_random_uuid(),
  created_at         timestamptz not null default now(),
  input_mode         text not null check (input_mode in ('image', 'text')),
  category           text not null,
  pack_type          text,
  image_path         text,                 -- file name inside the label-images bucket
  raw_text           text,
  avg_ocr_confidence real,
  verdict            text not null check (verdict in ('COMPLIANT','NON_COMPLIANT','NEEDS_REVIEW','EXEMPT')),
  fail_count         int  not null default 0,
  review_count       int  not null default 0,
  result             jsonb not null        -- full ScanResult (every field + rule_reference)
);

create index if not exists scans_created_at_idx on public.scans (created_at desc);
create index if not exists scans_verdict_idx    on public.scans (verdict);

-- The backend uses the service-role key (bypasses RLS). With RLS on and no policies,
-- nobody else (anon / authenticated keys) can read or write this table.
alter table public.scans enable row level security;

-- Private bucket for uploaded label photos.
insert into storage.buckets (id, name, public)
values ('label-images', 'label-images', false)
on conflict (id) do nothing;
