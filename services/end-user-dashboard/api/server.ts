import { createClient } from '@clickhouse/client';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import express from 'express';
import { createApp } from './app';
import { createRepository } from './repository';

const password = process.env.CLICKHOUSE_PASSWORD_FILE ? readFileSync(process.env.CLICKHOUSE_PASSWORD_FILE, 'utf8').trim() : process.env.CLICKHOUSE_PASSWORD;
if (!password) throw new Error('ClickHouse password is required');
const client = createClient({ url: process.env.CLICKHOUSE_URL ?? 'http://clickhouse:8123', username: process.env.CLICKHOUSE_USER ?? 'sentinel_dashboard_u', password });
const app = createApp(createRepository(client));
app.get('/healthz', (_req, res) => res.json({ status: 'ok' }));
app.use(express.static(resolve('dist')));
app.listen(Number(process.env.PORT ?? 3000), '0.0.0.0', () => console.log('Dashboard listening'));
