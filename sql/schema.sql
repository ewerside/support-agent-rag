-- Safe to run more than once.
-- Tables live in their own schema: the database is shared with other portfolio projects, and
-- Supabase only exposes the public schema through its REST API.
create extension if not exists vector;

create schema if not exists support_agent;

create table if not exists support_agent.orders (
    order_id text primary key,
    email text not null,
    customer_name text not null,
    country text not null,
    status text not null
        check (status in ('processing', 'shipped', 'delivered', 'returned', 'cancelled')),
    carrier text,
    tracking_number text,
    shipped_at date,
    eta date,
    items jsonb not null,
    total numeric(10, 2) not null,
    currency text not null
);

create table if not exists support_agent.kb_chunks (
    id text primary key,
    article_id text not null,
    title text not null,
    content text not null,
    embedding vector(384) not null
);

create index if not exists kb_chunks_embedding_idx
    on support_agent.kb_chunks using hnsw (embedding vector_cosine_ops);

-- search_path is pinned so the vector type and the <=> operator resolve the same way for every caller.
create or replace function support_agent.match_chunks(query_embedding vector(384), match_count int)
returns table (id text, article_id text, title text, content text, similarity float)
language sql
stable
set search_path = public
as $$
    select c.id, c.article_id, c.title, c.content, 1 - (c.embedding <=> query_embedding)
    from support_agent.kb_chunks c
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
