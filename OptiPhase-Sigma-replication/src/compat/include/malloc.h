/*
 * Compatibility shim for legacy sources that include <malloc.h>. macOS does not ship that
 * header; malloc and friends are declared in <stdlib.h>, so forward to it unchanged.
 */
#include <stdlib.h>
