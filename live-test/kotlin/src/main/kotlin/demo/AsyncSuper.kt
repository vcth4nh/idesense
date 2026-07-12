// Suspend-function super resolution: the suspend modifier must not stop
// AsyncImpl.fetch from resolving to the suspend fun declared in AsyncFetcher.
package demo

interface AsyncFetcher {
    suspend fun fetch(): String
}

class AsyncImpl : AsyncFetcher {
    override suspend fun fetch(): String = "fetched"
}
