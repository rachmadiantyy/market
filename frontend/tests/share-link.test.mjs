import test from 'node:test';
import assert from 'node:assert/strict';
import { validAffiliateLink, shareDestination, readActivity } from '../src/lib/share-link.ts';

test('only HTTP(S) URLs without embedded credentials are accepted', () => {
  for (const link of ['https://s.shopee.co.id/example?affiliate_id=123', 'http://example.com/item']) assert.equal(validAffiliateLink(link), true);
  for (const link of ['', 'javascript:alert(1)', 'data:text/html,test', 'file:///tmp/test', 'https://user:password@example.com', 'example.com']) assert.equal(validAffiliateLink(link), false);
});
test('affiliate tracking survives every platform URL encoding', () => {
  const original = 'https://example.com/p?affiliate_id=a%2Fb&campaign=rumah+cantik&next=https%3A%2F%2Fexample.com%2F#variant';
  const facebook = new URL(shareDestination('facebook', original, 'Catatan'));
  const threads = new URL(shareDestination('threads', original, 'Catatan'));
  const x = new URL(shareDestination('x', original, 'Catatan'));
  assert.equal(facebook.searchParams.get('u'), original);
  assert.equal(threads.searchParams.get('text'), 'Catatan\n\n' + original);
  assert.equal(x.searchParams.get('url'), original);
  assert.equal(x.searchParams.get('text'), 'Catatan');
  assert.equal(facebook.searchParams.has('text'), false);
});
test('bad links cannot generate a share destination', () => {
  assert.throws(() => shareDestination('x', 'javascript:alert(1)'));
});
test('corrupt, hostile and oversized browser history is safely bounded', () => {
  assert.deepEqual(readActivity('{bad json'), []);
  assert.deepEqual(readActivity('{}'), []);
  const row = { id: '1', title: 'Produk', link: 'https://example.com', platform: 'x', openedAt: '2026-11-05T12:00:00Z' };
  assert.deepEqual(readActivity(JSON.stringify([row, {...row, link:'javascript:alert(1)'}, {...row, platform:'unknown'}, {...row, openedAt:'broken'}])), [row]);
  assert.equal(readActivity(JSON.stringify(Array.from({length:120},()=>row))).length, 100);
});
