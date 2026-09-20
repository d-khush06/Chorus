const crypto = require('crypto');
const path = require('path');

const TICKET_TTL_MS = 15 * 60 * 1000; // 15 minutes TTL
const tickets = globalThis.__CHORUS_STREAM_TICKETS__ || new Map();
globalThis.__CHORUS_STREAM_TICKETS__ = tickets;

function generateTicket(userId, resourceId) {
  const now = Date.now();
  const ticket = {
    id: crypto.randomBytes(24).toString('hex'),
    userId: String(userId),
    resourceId: String(resourceId),
    createdAt: now,
    expiresAt: now + TICKET_TTL_MS,
    uses: 0,
    maxUses: 1000 // Multi-use ticket for video ranges and SSE reconnections
  };
  tickets.set(ticket.id, ticket);
  return ticket;
}

function validateTicket(ticketId, resourceId, userId = null) {
  if (!ticketId) return { valid: false, reason: 'No ticket provided' };
  const ticket = tickets.get(ticketId);
  if (!ticket) return { valid: false, reason: 'Ticket not found' };

  if (Date.now() > ticket.expiresAt) {
    tickets.delete(ticketId);
    return { valid: false, reason: 'Ticket expired' };
  }

  if (userId && ticket.userId !== String(userId)) {
    return { valid: false, reason: 'Ticket user mismatch' };
  }

  if (resourceId) {
    const target = String(resourceId);
    const stored = ticket.resourceId;
    const match = stored === '*' || 
                  stored === target || 
                  path.basename(stored) === path.basename(target);
    if (!match) {
      return { valid: false, reason: 'Ticket resource mismatch' };
    }
  }

  ticket.uses++;
  return { valid: true, ticket };
}

function getTicket(ticketId) {
  return tickets.get(ticketId) || null;
}

function cleanupExpiredTickets() {
  const now = Date.now();
  for (const [id, ticket] of tickets.entries()) {
    if (now > ticket.expiresAt) {
      tickets.delete(id);
    }
  }
}

// Periodic cleanup
setInterval(cleanupExpiredTickets, 60000);

module.exports = { generateTicket, validateTicket, getTicket, TICKET_TTL_MS };