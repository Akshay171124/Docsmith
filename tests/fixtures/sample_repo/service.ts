export function formatName(first: string, last: string): string {
  return `${first} ${last}`;
}

export class Cache {
  get(key: string): string | null {
    return null;
  }
}
