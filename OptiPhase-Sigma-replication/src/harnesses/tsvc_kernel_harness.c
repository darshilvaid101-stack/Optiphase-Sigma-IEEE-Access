/*
 * Harness for one TSVC kernel (Callahan, Dongarra, and Levine suite, float variant).
 *
 * The kernel and its data initialisation are compiled unmodified from tsc.inc. This file
 * only selects one kernel through KERNEL_FUNCTION and sets a small repetition count, so
 * that checksums are reproducible and runs stay short enough for lli.
 */

#define TYPE float
#define ALIGNMENT 16
#include "tests.h"

/* tsc.inc defines its own driver main(); rename it so that this harness owns main(). */
#define main tsvc_unused_driver_main
#include "tsc.inc"
#undef main

#ifndef KERNEL_FUNCTION
#error "compile with -DKERNEL_FUNCTION=<kernel name>, for example -DKERNEL_FUNCTION=s000"
#endif

#ifndef HARNESS_NTIMES
#define HARNESS_NTIMES 10
#endif

int main(void)
{
    ntimes = HARNESS_NTIMES;
    KERNEL_FUNCTION();
    return 0;
}
