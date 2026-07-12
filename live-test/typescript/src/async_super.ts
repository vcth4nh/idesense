// Async super fixture: AsyncImpl.fetch is an async override of AsyncFetcher.fetch —
// the async modifier must not hide the interface method as its super.
export interface AsyncFetcher {
    fetch(): Promise<string>;
}

export class AsyncImpl implements AsyncFetcher {
    async fetch(): Promise<string> { return "fetched"; }
}
