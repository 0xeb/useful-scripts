#include <math.h>
#include <stdio.h>
#include <stdint.h>

int main()
{
    uint64_t results[] = {<<expr>>};
    const char *exprs_str[] = {<<exprs_text>>};
    const char *exprs_titles[] = {<<exprs_titles>>};

    for (int i = 0; i < sizeof(results)/sizeof(results[0]); i++) 
        printf("<%s>\n"
        "%s\n"
        "\n"
        "    <hex=0x%I64x/>\n"
        "    <u64=%I64u/>\n"
        "    <i64=%I64d/>\n"
        "</%s>\n\n", 
        exprs_titles[i], 
            exprs_str[i], results[i], results[i], results[i],
        exprs_titles[i]);

    return 0;
}
