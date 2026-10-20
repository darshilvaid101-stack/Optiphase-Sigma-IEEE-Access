/*
 * Harness for one CoreMark kernel. The kernels and their data initialisation come unmodified
 * from core_list_join.c, core_matrix.c, core_state.c, and core_util.c. This file reproduces the
 * single-context setup that core_main.c performs (seeds, memory partitioning, and the list,
 * matrix, and state initialisers), then runs exactly one kernel and prints its result.
 *
 * Standalone kernels take fixed parameters: dtype 0x22 (the minimum CoreMark enforces for state
 * transitions) and a zero starting CRC. Inside CoreMark, dtype is derived from list data.
 */
#include <stdio.h>
#include "coremark.h"

ee_u16 crcu8(ee_u8 data, ee_u16 crc);
void matrix_mul_matrix_bitextract(ee_u32 N, MATRES *C, MATDAT *A, MATDAT *B);

#define HARNESS_SEED1 0
#define HARNESS_SEED2 0
#define HARNESS_SEED3 0x66
#define HARNESS_DTYPE 0x22
#define HARNESS_CRC_BYTES 1000

static ee_u8 harness_memory[TOTAL_DATA_SIZE];

static void partition_memory(core_results *results)
{
    ee_u32 part_size = TOTAL_DATA_SIZE / NUM_ALGORITHMS;
    ee_u32 part;
    results->memblock[0] = harness_memory;
    results->size       = part_size;
    for (part = 0; part < NUM_ALGORITHMS; part++)
        results->memblock[part + 1] = harness_memory + part_size * part;
}

static void initialise(core_results *results)
{
    results->seed1      = HARNESS_SEED1;
    results->seed2      = HARNESS_SEED2;
    results->seed3      = HARNESS_SEED3;
    results->iterations = 1;
    results->execs      = ID_LIST | ID_MATRIX | ID_STATE;
    partition_memory(results);
    results->list = core_list_init(results->size, (list_head *)results->memblock[1], results->seed1);
    core_init_matrix(results->size,
                     results->memblock[2],
                     (ee_s32)results->seed1 | (((ee_s32)results->seed2) << 16),
                     &(results->mat));
    core_init_state(results->size, results->seed1, (ee_u8 *)results->memblock[3]);
}

static void run_crc_loop(void)
{
    ee_u16 crc = 0;
    ee_u32 index;
    for (index = 0; index < HARNESS_CRC_BYTES; index++)
        crc = crcu8((ee_u8)(index & 0xff), crc);
    printf("crcu8 crc=%u\n", (unsigned)crc);
}

static void run_matrix_multiply(core_results *results)
{
    ee_u32 row, column;
    unsigned long checksum = 0;
    int size = results->mat.N;
    matrix_mul_matrix_bitextract((ee_u32)size, results->mat.C, results->mat.A, results->mat.B);
    for (row = 0; row < (ee_u32)size; row++)
        for (column = 0; column < (ee_u32)size; column++)
            checksum = checksum * 31 + (unsigned long)(ee_u32)results->mat.C[row * size + column];
    printf("matrix_mul_matrix_bitextract checksum=%lu\n", checksum);
}

int main(void)
{
    static core_results results;
    initialise(&results);
#if defined(RUN_LIST)
    printf("core_bench_list crc=%u\n", (unsigned)core_bench_list(&results, 1));
#elif defined(RUN_MATRIX)
    printf("core_bench_matrix crc=%u\n",
           (unsigned)core_bench_matrix(&(results.mat), HARNESS_DTYPE, 0));
#elif defined(RUN_STATE)
    printf("core_bench_state crc=%u\n",
           (unsigned)core_bench_state(results.size,
                                      (ee_u8 *)results.memblock[3],
                                      results.seed1,
                                      results.seed2,
                                      HARNESS_DTYPE,
                                      0));
#elif defined(RUN_CRCU8)
    run_crc_loop();
#elif defined(RUN_MATMUL)
    run_matrix_multiply(&results);
#else
#error "compile with one of -DRUN_LIST, -DRUN_MATRIX, -DRUN_STATE, -DRUN_CRCU8, -DRUN_MATMUL"
#endif
    return 0;
}
